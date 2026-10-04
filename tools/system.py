import re
import subprocess

from config import SUBPROCESS_TIMEOUT


def _run_osascript(script: str) -> bool:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            print("❌ AppleScript error:", (result.stderr or "").strip())
            return False
        return True
    except Exception as e:
        print(f"❌ System command error: {e}")
        return False


def _run_shell(cmd: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        ok = result.returncode == 0
        output = (result.stdout or result.stderr or "").strip()
        return ok, output
    except Exception as e:
        return False, str(e)


def _get_current_volume() -> int:
    script = "output volume of (get volume settings)"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            return 0
        return max(0, min(100, int((result.stdout or "0").strip())))
    except Exception:
        return 0


def get_output_volume() -> int:
    return _get_current_volume()


def is_output_muted() -> bool:
    script = "output muted of (get volume settings)"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            return False
        return (result.stdout or "").strip().lower() == "true"
    except Exception:
        return False


def set_volume(value: int) -> bool:
    value = max(0, min(100, int(value)))
    return _run_osascript(f"set volume output volume {value}")


def change_volume(delta: int) -> bool:
    current = _get_current_volume()
    return set_volume(current + delta)


def mute() -> bool:
    return _run_osascript("set volume with output muted")


def unmute() -> bool:
    return _run_osascript("set volume without output muted")


def brightness_up() -> bool:
    ok, output = _run_shell(["brightness", "0.1+"])
    if not ok:
        print("❌ Brightness up error:", output)
    return ok


def brightness_down() -> bool:
    ok, output = _run_shell(["brightness", "0.1-"])
    if not ok:
        print("❌ Brightness down error:", output)
    return ok


def lock_screen() -> bool:
    ok, output = _run_shell(
        ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"]
    )
    if not ok:
        print("❌ Lock screen error:", output)
    return ok


def sleep_display() -> bool:
    ok, output = _run_shell(["pmset", "displaysleepnow"])
    if not ok:
        print("❌ Sleep display error:", output)
    return ok


def read_clipboard() -> str | None:
    ok, output = _run_shell(["pbpaste"])
    if not ok:
        return None
    return output


def take_screenshot() -> str | None:
    import os
    import time

    path = os.path.expanduser(f"~/Desktop/Jarvis Screenshot {int(time.time())}.png")
    ok, output = _run_shell(["screencapture", "-x", path])
    if not ok or not os.path.isfile(path):
        print("❌ Screenshot error:", output)
        return None
    return path


def get_battery_status() -> str | None:
    ok, output = _run_shell(["pmset", "-g", "batt"])
    if not ok or not output:
        return None

    percent_match = re.search(r"(\d+)%", output)
    if not percent_match:
        return "I couldn't read the battery percentage."

    percent = percent_match.group(1)

    lowered = output.lower()
    # Check "discharging" before "charging" — "discharging" contains "charging"
    # as a substring, so checking charging first would misreport it.
    if "discharging" in lowered or "battery power" in output:
        charging_state = "not charging"
    elif "charging" in lowered or "ac power" in output:
        charging_state = "charging"
    else:
        charging_state = "in an unknown power state"

    return f"Your battery is at {percent} percent and is {charging_state}."