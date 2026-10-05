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

from tools import live
from tools.calendar import next_message as _calendar_next_message
from tools.calendar import today_message as _calendar_today_message
from tools.mail import unread_message as _mail_unread_message
from tools.media import (
    next_track,
    now_playing,
    pause_music,
    previous_track,
    resume_music,
)
from tools.notes import add_note
from tools.reminders import add_reminder
from tools.shortcuts import list_shortcuts
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


def _pause(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = pause_music()
    return ok, message, {}


def _resume(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = resume_music()
    return ok, message, {}


def _next_track(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = next_track()
    return ok, message, {}


def _previous_track(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = previous_track()
    return ok, message, {}


def _now_playing(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = now_playing()
    return ok, message, {}


def _calendar_today(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = _calendar_today_message()
    return ok, message, {}


def _calendar_next(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = _calendar_next_message()
    return ok, message, {}


def _mail_unread(_value: str | None = None) -> tuple[bool, str, dict]:
    ok, message = _mail_unread_message()
    return ok, message, {}


def _live(fn):
    """Wrap a tools.live function (value -> (ok, message)) as a registry handler."""
    def handler(value: str | None = None) -> tuple[bool, str, dict]:
        ok, message = fn(value)
        return ok, message, {}
    return handler


def _shortcuts_list(_value: str | None = None) -> tuple[bool, str, dict]:
    names = list_shortcuts()
    if not names:
        return True, "You don't have any shortcuts yet.", {}
    shown = ", ".join(names[:10])
    more = f", and {len(names) - 10} more" if len(names) > 10 else ""
    noun = "shortcut" if len(names) == 1 else "shortcuts"
    return True, f"You have {len(names)} {noun}: {shown}{more}.", {}


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
        SystemAction("pause", _pause),
        SystemAction("resume", _resume),
        SystemAction("next_track", _next_track),
        SystemAction("previous_track", _previous_track),
        SystemAction("now_playing", _now_playing),
        SystemAction("calendar_today", _calendar_today),
        SystemAction("calendar_next", _calendar_next),
        SystemAction("mail_unread", _mail_unread),
        SystemAction("shortcuts_list", _shortcuts_list),
        # Live data (tools/live.py): the value is optional (a city, topic, coin or "100 usd to eur").
        SystemAction("weather", _live(live.weather_now)),
        SystemAction("weather_tomorrow", _live(live.weather_tomorrow)),
        SystemAction("news", _live(live.news)),
        SystemAction("time_now", _live(live.time_now)),
        SystemAction("date_today", _live(live.date_today)),
        SystemAction("price", _live(live.price)),
        SystemAction("convert", _live(live.convert)),
        SystemAction("wiki", _live(live.wiki)),
        SystemAction("web_search", _live(live.web_search)),
    ]
}

# e.g. "volume_up|volume_down|mute|unmute|...|reminder_add|note_add"
SYSTEM_ACTIONS_PIPE_LIST = "|".join(SYSTEM_ACTIONS.keys())
