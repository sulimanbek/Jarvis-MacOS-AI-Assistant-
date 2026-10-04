"""
Single source of truth for "system" tool sub-actions.

Every system action (volume_up, battery_status, etc.) previously had to be
declared in four places by hand: the executor's dispatch chain, the LLM
brain's prompt, the plan validator's allowlist, and the agent planner's
prompt. Missing one meant an action the LLM could request but the executor
(or plan validator) didn't recognize — exactly what happened when
volume_status was added to the executor but not to plan_validator or the
agent prompt.

Add a new system action ONLY here; executor.py, plan_validator.py,
brain_local.py, and agent.py all derive their action lists (and, for
value-taking actions, their prompt examples) from this module.
"""

from collections.abc import Callable
from dataclasses import dataclass

from tools.notes import add_note
from tools.reminders import add_reminder
from tools.system import (
    brightness_down,
    brightness_up,
    change_volume,
    get_battery_status,
    get_output_volume,
    is_output_muted,
    lock_screen,
    mute,
    read_clipboard,
    sleep_display,
    take_screenshot,
    unmute,
)

# A handler takes one optional free-text value (unused by most actions) and
# returns (ok, message, data).
Handler = Callable[[str | None], tuple[bool, str, dict]]


@dataclass(frozen=True)
class SystemAction:
    name: str
    handler: Handler
    requires_value: bool = False
    value_hint: str = ""  # shown in LLM prompt examples, e.g. "reminder text"


def _volume_up(_value: str | None = None) -> tuple[bool, str, dict]:
    before = get_output_volume()
    ok = change_volume(10)
    after = get_output_volume()
    ok = ok and after >= before
    message = "Volume increased." if ok else "I couldn't increase the volume."
    return ok, message, {}


def _volume_down(_value: str | None = None) -> tuple[bool, str, dict]:
    before = get_output_volume()
    ok = change_volume(-10)
    after = get_output_volume()
    ok = ok and after <= before
    message = "Volume decreased." if ok else "I couldn't decrease the volume."
    return ok, message, {}


def _mute(_value: str | None = None) -> tuple[bool, str, dict]:
    ok = mute()
    if ok:
        ok = is_output_muted()
    message = "Muted." if ok else "I couldn't mute the volume."
    return ok, message, {}


def _unmute(_value: str | None = None) -> tuple[bool, str, dict]:
    ok = unmute()
    if ok:
        ok = not is_output_muted()
    message = "Unmuted." if ok else "I couldn't unmute the volume."
    return ok, message, {}


def _lock_screen(_value: str | None = None) -> tuple[bool, str, dict]:
    ok = lock_screen()
    message = "Locking screen." if ok else "I couldn't lock the screen."
    return ok, message, {}


def _sleep_display(_value: str | None = None) -> tuple[bool, str, dict]:
    ok = sleep_display()
    message = "Turning off the display." if ok else "I couldn't turn off the display."
    return ok, message, {}


def _volume_status(_value: str | None = None) -> tuple[bool, str, dict]:
    level = get_output_volume()
    muted = is_output_muted()
    ok = level >= 0
    if ok:
        message = f"Volume is at {level} percent" + (" and muted." if muted else ".")
    else:
        message = "I couldn't get the volume status."
    return ok, message, {"level": level, "muted": muted}


def _battery_status(_value: str | None = None) -> tuple[bool, str, dict]:
    status = get_battery_status()
    if not status:
        return False, "I couldn't get the battery status.", {}
    return True, status, {"status": status}


def _brightness_up(_value: str | None = None) -> tuple[bool, str, dict]:
    ok = brightness_up()
    message = "Brightness increased." if ok else "I couldn't increase the brightness."
    return ok, message, {}


def _brightness_down(_value: str | None = None) -> tuple[bool, str, dict]:
    ok = brightness_down()
    message = "Brightness decreased." if ok else "I couldn't decrease the brightness."
    return ok, message, {}


def _clipboard_read(_value: str | None = None) -> tuple[bool, str, dict]:
    content = read_clipboard()
    if not content:
        return False, "Your clipboard is empty.", {}
    spoken = content if len(content) <= 200 else content[:200] + "..."
    return True, f"Your clipboard contains: {spoken}", {"content": content}


def _screenshot(_value: str | None = None) -> tuple[bool, str, dict]:
    path = take_screenshot()
    ok = path is not None
    message = "Screenshot saved to your desktop." if ok else "I couldn't take a screenshot."
    return ok, message, {"path": path} if ok else {}


def _reminder_add(value: str | None = None) -> tuple[bool, str, dict]:
    text = (value or "").strip()
    if not text:
        return False, "What should I remind you of?", {}
    ok = add_reminder(text)
    message = f"Reminder added: {text}." if ok else "I couldn't add that reminder."
    return ok, message, {"text": text} if ok else {}


def _note_add(value: str | None = None) -> tuple[bool, str, dict]:
    text = (value or "").strip()
    if not text:
        return False, "What should the note say?", {}
    ok = add_note(text)
    message = "Note added." if ok else "I couldn't add that note."
    return ok, message, {"text": text} if ok else {}


SYSTEM_ACTIONS: dict[str, SystemAction] = {
    action.name: action
    for action in [
        SystemAction("volume_up", _volume_up),
        SystemAction("volume_down", _volume_down),
        SystemAction("mute", _mute),
        SystemAction("unmute", _unmute),
        SystemAction("lock_screen", _lock_screen),
        SystemAction("sleep_display", _sleep_display),
        SystemAction("volume_status", _volume_status),
        SystemAction("battery_status", _battery_status),
        SystemAction("brightness_up", _brightness_up),
        SystemAction("brightness_down", _brightness_down),
        SystemAction("clipboard_read", _clipboard_read),
        SystemAction("screenshot", _screenshot),
        SystemAction("reminder_add", _reminder_add, requires_value=True, value_hint="reminder text"),
        SystemAction("note_add", _note_add, requires_value=True, value_hint="note text"),
    ]
}

# e.g. "volume_up|volume_down|mute|unmute|...|reminder_add|note_add"
SYSTEM_ACTIONS_PIPE_LIST = "|".join(SYSTEM_ACTIONS.keys())
