"""
core/verifier.py

Verifies step success after execution.
For most tools, trusts the executor's ok flag.
For app launches, does an additional system-level check via osascript
so Jarvis can report "I couldn't open that" rather than silently moving on.
"""

import subprocess

from services.applescript import escape_applescript_text


def verify_step(step: dict, result: dict) -> bool:
    """
    Returns True if the step succeeded.
    Never raises — a broken verifier must not crash the agent.
    """
    try:
        if not result.get("ok"):
            return False

        tool = step.get("tool", "")

        if tool == "app":
            # Extra check: confirm the app actually appeared in process list
            app_name = step.get("name", "")
            if app_name:
                return _app_is_running(app_name)

        # All other tools: trust the executor result
        return True

    except Exception:
        # Verification failure must not abort the step — log and assume ok
        return bool(result.get("ok", False))


def _app_is_running(app_name: str) -> bool:
    """Ask System Events whether the app is in the running processes list."""
    escaped = escape_applescript_text(app_name)
    script = f'tell application "System Events" to (name of processes) contains "{escaped}"'
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip().lower() == "true"
    except Exception:
        return True  # Don't fail the step if osascript itself is unavailable
