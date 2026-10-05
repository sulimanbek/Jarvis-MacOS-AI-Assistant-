"""
Apple Music transport controls: pause, resume, next, previous, what's playing.

Every call checks that Music is already running first. Telling an application
to do something launches it, so "pause" with Music closed would otherwise open
the app just to pause nothing.
"""

import subprocess

from services.applescript import run_applescript

NOT_OPEN = "Music isn't open."


def _music_running() -> bool:
    try:
        result = run_applescript('application "Music" is running')
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and (result.stdout or "").strip().lower() == "true"


def _tell_music(command: str) -> bool:
    try:
        result = run_applescript(f'tell application "Music" to {command}')
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def pause_music() -> tuple[bool, str]:
    if not _music_running():
        return False, NOT_OPEN
    return (True, "Paused.") if _tell_music("pause") else (False, "I couldn't pause the music.")


def resume_music() -> tuple[bool, str]:
    if not _music_running():
        return False, NOT_OPEN
    return (True, "Resuming.") if _tell_music("play") else (False, "I couldn't resume the music.")


def next_track() -> tuple[bool, str]:
    if not _music_running():
        return False, NOT_OPEN
    return (True, "Next track.") if _tell_music("next track") else (False, "I couldn't skip the track.")


def previous_track() -> tuple[bool, str]:
    if not _music_running():
        return False, NOT_OPEN
    if _tell_music("previous track"):
        return True, "Previous track."
    return False, "I couldn't go back a track."


def now_playing() -> tuple[bool, str]:
    if not _music_running():
        return False, NOT_OPEN
    script = '''
    tell application "Music"
        if player state is playing or player state is paused then
            return (player state as string) & "|" & (name of current track) & "|" & (artist of current track)
        end if
        return "stopped"
    end tell
    '''
    try:
        result = run_applescript(script)
    except (subprocess.TimeoutExpired, OSError):
        return False, "I couldn't check what's playing."
    out = (result.stdout or "").strip()
    if result.returncode != 0:
        return False, "I couldn't check what's playing."
    if out == "stopped" or "|" not in out:
        return True, "Nothing is playing."
    state, _, rest = out.partition("|")
    name, _, artist = rest.partition("|")
    lead = "Paused on" if state.strip() == "paused" else "Playing"
    return True, f"{lead} {name} by {artist}." if artist else f"{lead} {name}."
