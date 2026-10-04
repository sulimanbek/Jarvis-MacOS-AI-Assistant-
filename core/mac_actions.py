"""
core/mac_actions.py

Runs actions that Claude asks for (the bridge's mac_action tool) through the same
validation, security policy and executor as a spoken command.

Claude's requests are held to a stricter standard than your own voice, because a
model can be steered by text it read (a web page, an email). So on top of the
normal policy:
  - browser / open / shortcut always need a spoken yes, whatever policy.json says
    — opening a URL can carry data out in the address;
  - clipboard_read and screenshot are refused — they hand private content to the
    model. They still work when *you* ask for them out loud.
"""

from collections.abc import Callable
from typing import Any

from audio.tts import speak
from core.executor import execute
from security.policy import requires_confirmation as _policy_requires_confirmation

# Always confirmed when Claude is the one asking.
MODEL_CONFIRM_TOOLS = {"browser", "open", "shortcut"}

# System actions Claude may not trigger.
MODEL_BLOCKED_SYSTEM_ACTIONS = {"clipboard_read", "screenshot"}

Confirmer = Callable[[dict], bool]
_confirmer: Confirmer | None = None


def set_confirmer(fn: Confirmer | None) -> None:
    """Register how to ask the user for a spoken yes/no (differs per entry point)."""
    global _confirmer
    _confirmer = fn


def _describe(decision: dict) -> str:
    tool = decision.get("tool")
    if tool == "browser":
        target = decision.get("target", "a website")
        query = decision.get("query")
        return f"Open {target}" + (f" and search for {query}" if query else "")
    if tool == "open":
        return f"Open {decision.get('target', 'something')}"
    if tool == "shortcut":
        return f"Run the shortcut {decision.get('name', '')}".strip()
    return f"Do a {tool} action"


def run_model_action(decision: dict, user_text: str = "") -> dict[str, Any]:
    """Validate, gate and execute one model-requested action. Never raises."""
    # Imported here: the router imports the Claude brain, which imports this.
    from core.router import _validate_decision

    candidate = {"tool": decision.get("tool"), **{k: v for k, v in decision.items() if k != "tool"}}
    validated = _validate_decision(candidate)

    if validated.get("tool") is None:
        return {"ok": False, "error": validated.get("response") or "That isn't something I can do."}

    tool = validated["tool"]

    if tool == "system" and validated.get("action") in MODEL_BLOCKED_SYSTEM_ACTIONS:
        return {"ok": False, "error": "I'm not allowed to do that on my own. You can ask me directly."}

    if tool in MODEL_CONFIRM_TOOLS or _policy_requires_confirmation(tool):
        if _confirmer is None:
            return {"ok": False, "error": "I can't ask for permission here, so I didn't do it."}
        speak(f"{_describe(validated)}.")
        if not _confirmer(validated):
            return {"ok": False, "error": "The user said no. Do not try again."}

    result = execute(validated, user_text or "(claude action)")
    return {"ok": bool(result.get("ok")), "message": result.get("message", "")}
