import json
import os

PROFILE_FILE = "memory/profile.json"


def _ensure_file():
    os.makedirs("memory", exist_ok=True)

    if not os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "w") as f:
            json.dump({}, f)


def _safe_read():
    _ensure_file()

    try:
        with open(PROFILE_FILE) as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("⚠️ Corrupted profile memory file. Resetting...")
        return {}
    except Exception as e:
        print("❌ Profile read error:", e)
        return {}


def _safe_write(data):
    _ensure_file()

    try:
        with open(PROFILE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("❌ Profile write error:", e)


def set_profile_value(key: str, value: str):
    data = _safe_read()
    data[key] = value
    _safe_write(data)


def get_profile_value(key: str, default=None):
    data = _safe_read()
    return data.get(key, default)


def get_all_profile():
    return _safe_read()