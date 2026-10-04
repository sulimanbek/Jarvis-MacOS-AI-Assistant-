"""
core/agent.py

Bounded multi-step AI agent for Jarvis.

Flow:
  1. Call planner LLM with strict JSON-only system prompt
  2. Validate the plan (tool allowlist, step count, required params)
  3. Execute each step through the existing executor
  4. Verify each step; retry once on retryable failures
  5. On verified failure, ask the planner to replan the remainder of the
     work given the failure reason (bounded to one replan per run)
  6. Speak progress updates and final result

Bounds:
  - Max 5 steps
  - Known tools only (enforced by plan_validator)
  - No shell command generation
  - No infinite loops (hard step limit, single replan per run)
"""

import json
import re

from audio.tts import speak
from core.brain_local import think_with_system
from core.executor import execute
from core.plan_validator import validate_plan
from core.router import APP_ALIASES
from core.system_actions import SYSTEM_ACTIONS, SYSTEM_ACTIONS_PIPE_LIST
from core.verifier import verify_step
from tools.browser import WEB_TARGETS, clean_target
from utils.logger import save_action

_KNOWN_APPS = ", ".join(sorted(set(APP_ALIASES.values())))
_KNOWN_SITES = ", ".join(sorted(set(WEB_TARGETS.keys())))
_VALUE_ACTIONS = ", ".join(a.name for a in SYSTEM_ACTIONS.values() if a.requires_value)


def _normalize_step(step: dict) -> dict:
    """Defensively correct planner mistakes the small local LLM tends to make:
    routing a known app (e.g. "Safari", "Spotify") through the "browser" or
    "music" tool with an invented target instead of the "app" tool. Falls
    back to "open" for genuinely unknown browser targets rather than
    trusting an LLM-invented URL."""
    if not isinstance(step, dict):
        return step

    if step.get("tool") == "music":
        query = clean_target((step.get("query") or "").strip())
        for alias, app_name in APP_ALIASES.items():
            if alias == query:
                return {"tool": "app", "name": app_name}
        return step

    if step.get("tool") != "browser":
        return step

    raw_target = (step.get("target") or "").strip()
    target = clean_target(raw_target)

    if target in WEB_TARGETS:
        return step

    for alias, app_name in APP_ALIASES.items():
        if alias == target or alias in target or target in alias:
            return {"tool": "app", "name": app_name}

    return {"tool": "open", "target": raw_target}


_PLANNER_PROMPT = """You are Jarvis's task planner. Given a user command, produce a JSON execution plan.

ALLOWED TOOLS:
  app      → {"tool": "app", "name": "<AppName>"}
  browser  → {"tool": "browser", "target": "<site or url>"}
  music    → {"tool": "music", "query": "<song or artist>"}
  system   → {"tool": "system", "action": "<@@SYSTEM_ACTIONS@@>"}
  shortcut → {"tool": "shortcut", "name": "<shortcut name>"}
  open     → {"tool": "open", "target": "<file or folder>"}

Known app names (use the "app" tool for these, NEVER "browser"): @@KNOWN_APPS@@
Known browser targets (use the "browser" tool ONLY for these sites): @@KNOWN_SITES@@
If a website is not in that list, use the "open" tool instead of "browser".
For system actions that need free text (@@VALUE_ACTIONS@@), include a "value" field with that text, e.g. {"tool": "system", "action": "reminder_add", "value": "call mom at 5pm"}.

RULES:
- Use ONLY the tools above.
- Maximum 5 steps, minimum 1.
- Never generate shell commands.
- If the request cannot be done with these tools, return steps: [].
- Output ONLY valid JSON — no markdown, no explanation.

FORMAT:
{
  "goal": "<one-line description>",
  "steps": [
    {"tool": "...", "<param>": "<value>"},
    ...
  ]
}"""


_REPLAN_PROMPT_TEMPLATE = """You are Jarvis's task planner. A previous plan hit a failure partway through.

Original user request: "{user_text}"
Original goal: {goal}

Steps already completed successfully:
{completed}

The step that failed:
{failed_step}
Failure reason: {failure_reason}

Produce a NEW JSON plan for what should happen next to satisfy the original
request, taking the failure into account (try a different app/target/query,
skip the failed action, or a different tool entirely if that one is stuck).
Do not repeat the already-completed steps. If nothing more can reasonably be
done, return an empty steps list.

ALLOWED TOOLS:
  app      → {{"tool": "app", "name": "<AppName>"}}
  browser  → {{"tool": "browser", "target": "<site or url>"}}
  music    → {{"tool": "music", "query": "<song or artist>"}}
  system   → {{"tool": "system", "action": "<@@SYSTEM_ACTIONS@@>"}}
  shortcut → {{"tool": "shortcut", "name": "<shortcut name>"}}
  open     → {{"tool": "open", "target": "<file or folder>"}}

Known app names (use the "app" tool for these, NEVER "browser"): @@KNOWN_APPS@@
Known browser targets (use the "browser" tool ONLY for these sites): @@KNOWN_SITES@@
If a website is not in that list, use the "open" tool instead of "browser".
For system actions that need free text (@@VALUE_ACTIONS@@), include a "value" field with that text.

RULES:
- Use ONLY the tools above.
- Maximum 5 steps, zero or more.
- Never generate shell commands.
- Output ONLY valid JSON — no markdown, no explanation.

FORMAT:
{{
  "goal": "<one-line description>",
  "steps": [
    {{"tool": "...", "<param>": "<value>"}},
    ...
  ]
}}"""

MAX_REPLANS = 1


def _parse_plan_json(raw: str | None) -> dict | None:
    if not raw:
        return None

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Extract the first JSON object from the response
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _parse_plan_dict(raw: str | None) -> dict | None:
    """Like _parse_plan_json, but also guards against a technically-valid JSON
    payload that isn't a dict (e.g. a bare list/number/string), which would
    otherwise crash callers doing `.get("steps")` on it."""
    parsed = _parse_plan_json(raw)
    return parsed if isinstance(parsed, dict) else None


def _build_planner_prompt() -> str:
    return (
        _PLANNER_PROMPT
        .replace("@@KNOWN_APPS@@", _KNOWN_APPS)
        .replace("@@KNOWN_SITES@@", _KNOWN_SITES)
        .replace("@@SYSTEM_ACTIONS@@", SYSTEM_ACTIONS_PIPE_LIST)
        .replace("@@VALUE_ACTIONS@@", _VALUE_ACTIONS)
    )


def _call_planner(user_text: str) -> dict | None:
    """Ask the LLM to produce a structured plan. Returns parsed dict or None."""
    raw = think_with_system(user_text, _build_planner_prompt(), include_context=True)
    return _parse_plan_dict(raw)


def _call_replanner(
    user_text: str,
    goal: str,
    completed_descriptions: list[str],
    failed_step: dict,
    failure_reason: str,
) -> dict | None:
    """Ask the LLM to produce a follow-up plan given a step failure. Returns parsed dict or None."""
    prompt = _REPLAN_PROMPT_TEMPLATE.format(
        user_text=user_text,
        goal=goal,
        completed="\n".join(f"- {d}" for d in completed_descriptions) or "(none)",
        failed_step=json.dumps(failed_step),
        failure_reason=failure_reason or "unknown",
    )
    prompt = (
        prompt
        .replace("@@KNOWN_APPS@@", _KNOWN_APPS)
        .replace("@@KNOWN_SITES@@", _KNOWN_SITES)
        .replace("@@SYSTEM_ACTIONS@@", SYSTEM_ACTIONS_PIPE_LIST)
        .replace("@@VALUE_ACTIONS@@", _VALUE_ACTIONS)
    )
    raw = think_with_system(user_text, prompt, include_context=True)
    return _parse_plan_dict(raw)


def _describe_step(step: dict) -> str:
    """Human-readable one-liner for a plan step (used in progress TTS)."""
    tool = step.get("tool", "")
    if tool == "app":
        return f"opening {step.get('name', 'the app')}"
    if tool == "browser":
        return f"going to {step.get('target', 'the site')}"
    if tool == "music":
        return f"playing {step.get('query', 'music')}"
    if tool == "system":
        return step.get("action", "system action").replace("_", " ")
    if tool == "shortcut":
        return f"running {step.get('name', 'the shortcut')}"
    if tool == "open":
        return f"opening {step.get('target', 'the file')}"
    return tool


def run_agent(user_text: str, confirm_step=None) -> dict:
    """
    Execute a multi-step plan for user_text.

    confirm_step: optional callable(step: dict) -> bool. Called before each
    step is executed; if it returns False the step (and the run) is treated
    as denied. Lets callers apply the same confirmation policy that gates
    single-tool execution, since planned steps can hit high-risk tools too.

    Returns {"ok": bool, "message": str}.
    """
    speak("Let me plan that.")

    plan = _call_planner(user_text)
    if not plan:
        speak("I couldn't build a plan for that.")
        save_action("agent", user_text, "failure", "Planner returned nothing")
        return {"ok": False, "message": "Planner returned no plan"}

    plan["steps"] = [_normalize_step(s) for s in plan.get("steps", [])]

    validation = validate_plan(plan)
    if not validation.valid:
        speak("I can't do that with my current permissions.")
        save_action("agent", user_text, "failure", f"Plan invalid: {validation.error}")
        return {"ok": False, "message": f"Plan rejected: {validation.error}"}

    steps = plan.get("steps", [])
    if not steps:
        speak("I'm not sure how to do that.")
        return {"ok": False, "message": "Empty plan"}

    goal = plan.get("goal", user_text)
    total = len(steps)
    if total > 1:
        speak(f"On it. {total} steps.")

    completed_descriptions: list[str] = []
    replans_used = 0
    last_result: dict = {}
    step_num = 0

    i = 0
    while i < len(steps):
        step = steps[i]
        step_num += 1

        if confirm_step is not None and not confirm_step(step):
            speak("Cancelled.")
            save_action("agent", user_text, "failure", f"Step {step_num} denied: {step}")
            return {"ok": False, "message": f"Step {step_num} was not confirmed."}

        if len(steps) > 1:
            speak(f"Step {step_num}: {_describe_step(step)}.")

        result = execute(step, user_text)

        if not verify_step(step, result) and result.get("retryable"):
            speak("Retrying.")
            result = execute(step, user_text)

        ok = verify_step(step, result)
        save_action(
            action_type=f"agent_step_{step_num}",
            user_input=user_text,
            result="success" if ok else "failure",
            details=str(result),
        )

        if not ok:
            failure_reason = result.get("message") or "Step failed verification"

            if replans_used < MAX_REPLANS:
                replans_used += 1
                speak("That didn't work. Let me try a different way.")

                new_plan = _call_replanner(user_text, goal, completed_descriptions, step, failure_reason)
                if new_plan:
                    new_plan["steps"] = [_normalize_step(s) for s in new_plan.get("steps", [])]
                new_steps = new_plan.get("steps") if new_plan else None

                if new_steps and validate_plan(new_plan).valid:
                    steps = steps[:i] + new_steps
                    continue

            speak(f"Step {step_num} failed. Stopping.")
            return {
                "ok": False,
                "message": failure_reason or f"Failed at step {step_num}.",
            }

        completed_descriptions.append(_describe_step(step))
        last_result = result
        i += 1

    total = len(steps)
    if total > 1:
        speak("All done.")
        return {"ok": True, "message": f"Completed {total} steps."}

    # Single-step agent: speak the executor's message
    response = (last_result.get("message") or "Done.").strip()
    speak(response)
    return {"ok": True, "message": response}
