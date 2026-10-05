"""
Read-only summary of unread mail in the Mail app: how many, and the newest few.

It never sends, replies, deletes or opens a message. Only senders and subjects
are read out. The first run makes macOS ask whether this program may control Mail.
"""

import subprocess

from services.applescript import run_applescript

TIMEOUT = 30
LOOK_AT = 30   # newest messages to scan for unread ones; keeps huge inboxes fast
SHOW = 3

PERMISSION_HELP = (
    "I couldn't read your mail. Allow it under System Settings, Privacy and "
    "Security, Automation, and make sure Mail has an account."
)

_SCRIPT = f'''
tell application "Mail"
    set n to unread count of inbox
    set out to (n as string) & linefeed
    set total to count of messages of inbox
    set lim to total
    if lim > {LOOK_AT} then set lim to {LOOK_AT}
    set found to 0
    repeat with i from 1 to lim
        set m to message i of inbox
        if read status of m is false then
            set out to out & (extract name from sender of m) & "|" & (subject of m) & linefeed
            set found to found + 1
            if found >= {SHOW} then exit repeat
        end if
    end repeat
end tell
return out
'''


def parse(raw: str) -> tuple[int, list[tuple[str, str]]] | None:
    lines = [ln for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        count = int(lines[0].strip())
    except ValueError:
        return None
    items = []
    for line in lines[1:]:
        sender, _, subject = line.partition("|")
        items.append((sender.strip() or "Unknown", subject.strip() or "no subject"))
    return count, items


def unread_message() -> tuple[bool, str]:
    try:
        result = run_applescript(_SCRIPT, timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return False, PERMISSION_HELP
    if result.returncode != 0:
        return False, PERMISSION_HELP
    parsed = parse(result.stdout or "")
    if parsed is None:
        return False, PERMISSION_HELP
    count, items = parsed
    if count == 0:
        return True, "You have no unread email."
    lead = "You have 1 unread email" if count == 1 else f"You have {count} unread emails"
    if not items:
        return True, lead + "."
    latest = "; ".join(f"{sender} about {subject}" for sender, subject in items)
    return True, f"{lead}. The latest: {latest}."
