"""
core/brain_claude.py

Claude as the brain for requests the regex fast-path can't handle. Same shape as
brain_local.think_local: returns a router decision, or None when Claude can't be
reached so the caller can fall back to Ollama.
"""

from core.bridge_client import BridgeError, BridgeUnavailable, get_client
from core.mac_actions import run_model_action


def think_claude(user_text: str) -> dict | None:
    """
    Ask Claude. Returns {"tool": None, "response": ...} on success.
    Returns None when the bridge is unreachable or Claude's turn failed (fall back).
    A timeout returns a spoken apology instead of falling back, because Claude may
    already have started an action and a second brain shouldn't repeat it.
    """
    try:
        reply = get_client().ask(
            user_text,
            on_action=lambda decision: run_model_action(decision, user_text),
        )
    except BridgeUnavailable as e:
        print(f"[Claude] unavailable: {e}")
        return None
    except BridgeError as e:
        print(f"[Claude] turn failed: {e}")
        return None
    except TimeoutError:
        print("[Claude] timed out")
        return {
            "tool": None,
            "response": "That took too long, so I stopped.",
            "_unhandled_reason": "claude_timeout",
        }

    if not reply:
        return None
    return {"tool": None, "response": reply, "_source": "claude"}
