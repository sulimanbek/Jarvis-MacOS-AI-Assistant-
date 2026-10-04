import json

from config import OLLAMA_MODEL, PERSONALITY_MODE
from core.system_actions import SYSTEM_ACTIONS
from memory.context import (
    get_last_action,
    get_last_app,
    get_last_browser_target,
    get_last_messages,
    get_last_shortcut,
    get_last_song,
)
from services.ollama_service import ask_ollama
from tools.browser import WEB_TARGETS

MAX_CONTEXT_TURNS = 6


PERSONALITY_PROMPTS = {
    "smooth": """
You are Jarvis, a smart macOS assistant.
Your tone is calm, polished, and natural.
Keep responses concise, smooth, and helpful.
Avoid sounding robotic or overly formal.
""",
    "siri": """
You are Jarvis, a polished macOS assistant.
Your tone is clear, calm, smooth, and assistant-like.
Keep responses short, confident, and natural.
Do not ramble.
""",
    "professional": """
You are Jarvis, a professional macOS assistant.
Your tone is clear, concise, and formal.
Be helpful and direct.
""",
    "chill": """
You are Jarvis, a relaxed and friendly macOS assistant.
Your tone is natural, light, and easygoing.
Keep responses short and smooth.
""",
}


SYSTEM_PROMPT = """
You are Jarvis, a local macOS assistant.

IMPORTANT:
Return ONLY valid JSON.
Do not include markdown.
Do not include explanations outside JSON.
Do not wrap JSON in code blocks.

Your job is to classify the user's intent.

====================
VALID OUTPUT FORMATS
====================

1) APP
{ "tool": "app", "name": "Safari" }

2) MUSIC
{ "tool": "music", "query": "Starboy" }

3) BROWSER
{ "tool": "browser", "target": "youtube" }

Only use "target" values from this exact list of known sites: {{BROWSER_TARGETS}}
If the requested site is not in that list, use the OPEN tool instead (case 4), not browser.

4) OPEN UNKNOWN TARGET
{ "tool": "open", "target": "something" }

5) SHORTCUT
{ "tool": "shortcut", "name": "Shortcut Name" }

6) SYSTEM ACTIONS
{{SYSTEM_ACTION_EXAMPLES}}

7) GENERAL RESPONSE
{ "tool": null, "response": "..." }

====================
ALLOWED TOOLS
====================

- app
- music
- browser
- open
- shortcut
- system
- null

====================
RULES
====================

- For obvious app requests → app
- For known websites (see the BROWSER target list above) → browser
- For any other website or opening request → open
- For system commands like volume, mute, battery → system
- For general knowledge, factual, or conversational questions with NO macOS
  action associated (e.g. trivia, opinions, small talk, "what is X", "how do
  I", "tell me about Y") → use tool: null with a real answer in "response".
  NEVER default to opening an app, a website, or any other tool just
  because you are unsure — if in doubt and no clear action is requested,
  use tool: null.
- Keep general replies short
- Always output JSON only

Examples:

User: "open safari"
→ { "tool": "app", "name": "Safari" }

User: "go to google mail"
→ { "tool": "browser", "target": "gmail" }

User: "open some obscure blog"
→ { "tool": "open", "target": "some obscure blog" }

User: "volume up"
→ { "tool": "system", "action": "volume_up" }

User: "mute"
→ { "tool": "system", "action": "mute" }

User: "what's the current volume"
→ { "tool": "system", "action": "volume_status" }

User: "what is AI"
→ { "tool": null, "response": "AI stands for artificial intelligence." }

User: "what is the capital of France"
→ { "tool": null, "response": "Paris." }

User: "tell me a joke"
→ { "tool": null, "response": "Why don't eggs tell jokes? They'd crack each other up." }
"""


_KNOWN_BROWSER_TARGETS = ", ".join(sorted(set(WEB_TARGETS.keys())))


def _system_action_example(action) -> str:
    if action.requires_value:
        return f'{{ "tool": "system", "action": "{action.name}", "value": "<{action.value_hint}>" }}'
    return f'{{ "tool": "system", "action": "{action.name}" }}'


_SYSTEM_ACTION_EXAMPLES = "\n".join(_system_action_example(a) for a in SYSTEM_ACTIONS.values())


def _build_system_prompt() -> str:
    personality = PERSONALITY_PROMPTS.get(
        PERSONALITY_MODE,
        PERSONALITY_PROMPTS["smooth"]
    )
    prompt = SYSTEM_PROMPT.replace("{{BROWSER_TARGETS}}", _KNOWN_BROWSER_TARGETS)
    prompt = prompt.replace("{{SYSTEM_ACTION_EXAMPLES}}", _SYSTEM_ACTION_EXAMPLES)
    return f"{personality}\n\n{prompt}"


def _build_state_block() -> str:
    """Compact summary of recent action state, so the LLM can resolve
    references like 'it', 'that', or 'again' without a fast-path regex."""
    last_action = get_last_action() or {}

    lines = []
    last_song = get_last_song()
    if last_song:
        lines.append(f"- last song played: {last_song}")

    last_app = get_last_app()
    if last_app:
        lines.append(f"- last app opened: {last_app}")

    last_browser_target = get_last_browser_target()
    if last_browser_target:
        lines.append(f"- last browser target: {last_browser_target}")

    last_shortcut = get_last_shortcut()
    if last_shortcut:
        lines.append(f"- last shortcut run: {last_shortcut}")

    if last_action.get("type"):
        lines.append(f"- last action: {last_action['type']} -> {last_action.get('value')}")

    if not lines:
        return ""

    return (
        "KNOWN CONTEXT (use only to resolve references like 'it'/'that'/'again'; "
        "do not mention this block or restate it unasked):\n" + "\n".join(lines)
    )


def _build_history_messages(current_user_text: str) -> list[dict]:
    """Recent conversation turns, excluding the current utterance (which is
    already the last entry in context.json since callers log it before routing)."""
    history = get_last_messages()

    if history and history[-1].get("role") == "user" and history[-1].get("text") == current_user_text:
        history = history[:-1]

    trimmed = history[-MAX_CONTEXT_TURNS:]
    return [
        {"role": msg["role"], "content": msg["text"]}
        for msg in trimmed
        if msg.get("text") and msg.get("role") in ("user", "assistant")
    ]


def think_with_system(user_text: str, system_prompt: str, include_context: bool = False) -> str | None:
    """
    Call Ollama with a fully custom system prompt.
    Returns the raw response string (not parsed).
    Used by the agent planner which needs JSON it parses itself.

    include_context=True adds recent conversation history + known action
    state, so multi-step plans can resolve references like "open it again".
    """
    full_prompt = system_prompt
    history_messages: list[dict] = []

    if include_context:
        state_block = _build_state_block()
        if state_block:
            full_prompt = f"{system_prompt}\n\n{state_block}"
        history_messages = _build_history_messages(user_text)

    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_text})
    return ask_ollama(messages, model=OLLAMA_MODEL)


def think_local(user_text: str) -> dict:
    system_prompt = _build_system_prompt()
    state_block = _build_state_block()
    if state_block:
        system_prompt = f"{system_prompt}\n\n{state_block}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_build_history_messages(user_text))
    messages.append({"role": "user", "content": user_text})

    raw = ask_ollama(messages, model=OLLAMA_MODEL)

    if not raw:
        return {
            "tool": None,
            "response": "I'm having trouble connecting to my local model right now."
        }

    try:
        parsed = json.loads(raw)

        if not isinstance(parsed, dict):
            return {
                "tool": None,
                "response": "I had trouble understanding that."
            }

        return parsed

    except json.JSONDecodeError:
        return {
            "tool": None,
            "response": raw.strip()
        }