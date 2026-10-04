import json
import os
from datetime import datetime

from config import ACTIONS_LOG_FILE


def _ensure_file():
    os.makedirs(os.path.dirname(ACTIONS_LOG_FILE), exist_ok=True)

    if not os.path.exists(ACTIONS_LOG_FILE):
        with open(ACTIONS_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


def _safe_read():
    try:
        with open(ACTIONS_LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("⚠️ Corrupted actions log. Resetting...")
        _safe_write([])
        return []
    except Exception as e:
        print("❌ Actions log read error:", e)
        return []


def _safe_write(data):
    try:
        temp_path = f"{ACTIONS_LOG_FILE}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, ACTIONS_LOG_FILE)
    except Exception as e:
        print("❌ Actions log write error:", e)


def save_action(action_type, user_input, result, details=""):
    _ensure_file()

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": action_type,
        "input": user_input,
        "result": result,
        "details": details,
    }

    data = _safe_read()
    data.append(entry)
    _safe_write(data)


def get_last_action():
    _ensure_file()
    data = _safe_read()
    return data[-1] if data else None


def get_last_successful_action():
    _ensure_file()
    data = _safe_read()

    for item in reversed(data):
        if item.get("result") == "success":
            return item

    return None


def get_last_action_of_type(action_type: str):
    _ensure_file()
    data = _safe_read()

    for item in reversed(data):
        if item.get("type") == action_type and item.get("result") == "success":
            return item

    return None


def get_unhandled_requests(limit: int = 20) -> list:
    """Requests Jarvis genuinely couldn't handle (as opposed to a normal
    conversational reply) — review these to spot patterns worth adding as
    new fast-paths, tools, or system actions."""
    _ensure_file()
    data = _safe_read()

    unhandled = [item for item in data if item.get("type") == "unhandled"]
    return unhandled[-limit:]