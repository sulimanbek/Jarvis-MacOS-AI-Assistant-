import json
import os

from config import CONTEXT_FILE_PATH

MAX_HISTORY = 10


def _ensure_file():
    os.makedirs(os.path.dirname(CONTEXT_FILE_PATH), exist_ok=True)

    if not os.path.exists(CONTEXT_FILE_PATH):
        with open(CONTEXT_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "messages": [],
                "state": {}
            }, f, indent=2)


def _safe_read():
    _ensure_file()

    try:
        with open(CONTEXT_FILE_PATH, encoding="utf-8") as f:
            data = json.load(f)

        # auto-upgrade old format: []
        if isinstance(data, list):
            upgraded = {
                "messages": data[-MAX_HISTORY:],
                "state": {}
            }
            _safe_write(upgraded)
            return upgraded

        if not isinstance(data, dict):
            upgraded = {"messages": [], "state": {}}
            _safe_write(upgraded)
            return upgraded

        data.setdefault("messages", [])
        data.setdefault("state", {})
        return data

    except json.JSONDecodeError:
        print("⚠️ Context file corrupted. Resetting...")
        upgraded = {"messages": [], "state": {}}
        _safe_write(upgraded)
        return upgraded
    except Exception as e:
        print("❌ Context read error:", e)
        return {"messages": [], "state": {}}


def _safe_write(data):
    try:
        temp_path = f"{CONTEXT_FILE_PATH}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CONTEXT_FILE_PATH)
    except Exception as e:
        print("❌ Context write error:", e)


# ---------- CHAT HISTORY ----------

def add_message(role: str, text: str):
    data = _safe_read()

    messages = data.get("messages", [])
    messages.append({
        "role": role,
        "text": text
    })

    data["messages"] = messages[-MAX_HISTORY:]
    _safe_write(data)


def get_last_messages():
    return _safe_read().get("messages", [])


def get_last_user_message():
    messages = get_last_messages()

    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("text")

    return None


# ---------- STATE HELPERS ----------

def _set_state_value(key: str, value):
    data = _safe_read()
    data["state"][key] = value
    _safe_write(data)


def _get_state_value(key: str, default=None):
    return _safe_read().get("state", {}).get(key, default)


# ---------- MUSIC ----------

def set_last_song(song: str):
    _set_state_value("last_song", song)


def get_last_song():
    return _get_state_value("last_song")


# ---------- APPS ----------

def set_last_app(app: str):
    _set_state_value("last_app", app)


def get_last_app():
    return _get_state_value("last_app")


# ---------- BROWSER ----------

def set_last_browser_target(target: str):
    _set_state_value("last_browser_target", target)


def get_last_browser_target():
    return _get_state_value("last_browser_target")


# ---------- SHORTCUTS ----------

def set_last_shortcut(name: str):
    _set_state_value("last_shortcut", name)


def get_last_shortcut():
    return _get_state_value("last_shortcut")


# ---------- LAST ACTION ----------

def set_last_action(action_type: str, value: str):
    _set_state_value("last_action", {
        "type": action_type,
        "value": value
    })


def get_last_action():
    return _get_state_value("last_action", {})