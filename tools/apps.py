import re
import subprocess

from config import SUBPROCESS_TIMEOUT
from services.applescript import escape_applescript_text

APP_ALIASES = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "safari": "Safari",
    "app store": "App Store",
    "store": "App Store",
    "music": "Music",
    "apple music": "Music",
    "photos": "Photos",
    "photo": "Photos",
    "messages": "Messages",
    "imessage": "Messages",
    "message": "Messages",
    "messenger": "Messenger",
    "facebook messenger": "Messenger",
    "finder": "Finder",
    "notes": "Notes",
    "calendar": "Calendar",
    "mail": "Mail",
    "gmail": "Mail",
    "facetime": "FaceTime",
    "settings": "System Settings",
    "system settings": "System Settings",
    "preferences": "System Settings",
    "terminal": "Terminal",
    "spotify": "Spotify",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "discord": "Discord",
    "visual studio code": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "pycharm": "PyCharm",
}


def clean_app_name(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\b(open|launch|start|the|app|application)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_candidates(app_name: str) -> list[str]:
    raw = (app_name or "").strip()
    lowered = clean_app_name(raw)

    candidates = []

    # 1) exact alias match
    if lowered in APP_ALIASES:
        candidates.append(APP_ALIASES[lowered])

    # 2) exact cleaned/raw names
    if raw:
        candidates.append(raw)
        candidates.append(raw.title())

    # 3) partial alias match, but only when meaningfully related
    for alias, resolved in APP_ALIASES.items():
        if lowered and (alias == lowered or alias in lowered or lowered in alias):
            candidates.append(resolved)

    # de-duplicate while preserving order
    unique = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            unique.append(candidate)
            seen.add(candidate)

    return unique


def open_app(app_name: str) -> bool:
    if not app_name or not app_name.strip():
        print("❌ No app name provided.")
        return False

    raw = app_name.strip()
    lowered = clean_app_name(raw)

    print(f"🧩 Requested app: {raw}")
    print(f"🧼 Cleaned app: {lowered}")

    candidates = _build_candidates(raw)
    print(f"🔍 Trying candidates: {candidates}")

    for candidate in candidates:
        try:
            result = subprocess.run(
                ["open", "-a", candidate],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )

            if result.returncode == 0:
                print(f"✅ Opened app: {candidate}")
                return True

            print(f"⚠️ Failed '{candidate}': {(result.stderr or '').strip()}")

        except Exception as e:
            print(f"❌ Exception opening '{candidate}': {e}")

    print("❌ App not found after trying all candidates.")
    return False


def is_app_running(app_name: str) -> bool:
    cleaned = clean_app_name(app_name or "")
    if not cleaned:
        return False

    candidates = _build_candidates(app_name)
    for candidate in candidates:
        escaped = escape_applescript_text(candidate)
        script = f'tell application "System Events" to (name of processes) contains "{escaped}"'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
            if result.returncode == 0 and (result.stdout or "").strip().lower() == "true":
                return True
        except Exception:
            continue

    return False