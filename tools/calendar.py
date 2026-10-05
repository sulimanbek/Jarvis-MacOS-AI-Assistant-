"""
Read today's events, or the next one, from the Calendar app.

Read-only. It asks Calendar through AppleScript, so the first run makes macOS ask
whether this program may control Calendar.

Known limit: events that repeat are reported by their original entry, so a
weekly meeting may be missed on the days after the first.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta

from services.applescript import run_applescript

# Calendar can be slow with many calendars, so allow more than the default.
TIMEOUT = 30
MAX_SPOKEN = 6

PERMISSION_HELP = (
    "I couldn't read your calendar. Allow it under System Settings, Privacy and "
    "Security, Automation."
)

_SCRIPT = '''
set d1 to {start}
set d2 to d1 + ({days} * days)
set out to ""
tell application "Calendar"
    repeat with c in calendars
        try
            set evs to (every event of c whose start date >= d1 and start date < d2)
            repeat with e in evs
                set s to start date of e
                set mm to (minutes of s) as string
                if (count of mm) < 2 then set mm to "0" & mm
                set out to out & (year of s) & "-" & ((month of s) as integer) & "-" & (day of s) & " " & (hours of s) & ":" & mm & "|" & ((allday event of e) as string) & "|" & (summary of e) & linefeed
            end repeat
        end try
    end repeat
end tell
return out
'''

_TODAY_START = "(current date)\nset time of d1 to 0"


@dataclass(frozen=True)
class Event:
    start: datetime
    all_day: bool
    title: str


def parse_events(raw: str) -> list[Event]:
    """Parse the AppleScript output; malformed lines are skipped."""
    events = []
    for line in (raw or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        stamp, all_day, title = parts
        try:
            start = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        events.append(Event(start, all_day.strip().lower() == "true", title.strip() or "Untitled"))
    return sorted(events, key=lambda e: (not e.all_day, e.start))


def fetch(days: int, from_midnight: bool) -> list[Event] | None:
    """Events in the window, or None if Calendar couldn't be read."""
    script = _SCRIPT.format(start=_TODAY_START if from_midnight else "(current date)", days=days)
    try:
        result = run_applescript(script, timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return parse_events(result.stdout or "")


def _say_time(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    suffix = "AM" if dt.hour < 12 else "PM"
    return f"{hour} {suffix}" if dt.minute == 0 else f"{hour}:{dt.minute:02d} {suffix}"


def _say_day(dt: datetime, now: datetime) -> str:
    delta = (dt.date() - now.date()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return dt.strftime("%A")


def today_message(now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now()
    events = fetch(days=1, from_midnight=True)
    if events is None:
        return False, PERMISSION_HELP
    if not events:
        return True, "Your calendar is clear today."

    parts = [("all day " if e.all_day else f"{_say_time(e.start)} ") + e.title for e in events]
    shown, extra = parts[:MAX_SPOKEN], len(parts) - MAX_SPOKEN
    count = "1 event" if len(events) == 1 else f"{len(events)} events"
    tail = f", and {extra} more" if extra > 0 else ""
    return True, f"You have {count} today: " + ", ".join(shown) + tail + "."


def next_message(now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now()
    events = fetch(days=7, from_midnight=False)
    if events is None:
        return False, PERMISSION_HELP
    upcoming = sorted((e for e in events if not e.all_day and e.start >= now - timedelta(minutes=1)),
                      key=lambda e: e.start)
    if not upcoming:
        return True, "Nothing coming up in the next week."
    e = upcoming[0]
    return True, f"Your next event is {e.title}, {_say_day(e.start, now)} at {_say_time(e.start)}."
