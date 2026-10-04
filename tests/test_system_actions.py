import core.system_actions as system_actions


def _handler(name):
    return system_actions.SYSTEM_ACTIONS[name].handler


# --- volume up / down, including before==after boundary case --------------

def test_volume_up_success_when_volume_increases(monkeypatch):
    monkeypatch.setattr(system_actions, "get_output_volume", lambda: 30)
    monkeypatch.setattr(system_actions, "change_volume", lambda delta: True)
    # after() will be called a second time by the handler; simulate rising volume
    calls = {"n": 0}

    def fake_get_volume():
        calls["n"] += 1
        return 30 if calls["n"] == 1 else 40

    monkeypatch.setattr(system_actions, "get_output_volume", fake_get_volume)

    ok, message, data = _handler("volume_up")(None)

    assert ok is True
    assert message == "Volume increased."
    assert data == {}


def test_volume_up_boundary_before_equals_after_still_counts_as_success(monkeypatch):
    # Volume was already at max: before == after. The handler only fails
    # if the volume actually dropped, so an unchanged (but not decreased)
    # reading is still reported as success.
    monkeypatch.setattr(system_actions, "get_output_volume", lambda: 100)
    monkeypatch.setattr(system_actions, "change_volume", lambda delta: True)

    ok, message, data = _handler("volume_up")(None)

    assert ok is True
    assert message == "Volume increased."


def test_volume_up_failure_when_change_volume_reports_failure(monkeypatch):
    monkeypatch.setattr(system_actions, "get_output_volume", lambda: 100)
    monkeypatch.setattr(system_actions, "change_volume", lambda delta: False)

    ok, message, data = _handler("volume_up")(None)

    assert ok is False
    assert message == "I couldn't increase the volume."


def test_volume_down_success_when_volume_decreases(monkeypatch):
    calls = {"n": 0}

    def fake_get_volume():
        calls["n"] += 1
        return 50 if calls["n"] == 1 else 40

    monkeypatch.setattr(system_actions, "get_output_volume", fake_get_volume)
    monkeypatch.setattr(system_actions, "change_volume", lambda delta: True)

    ok, message, data = _handler("volume_down")(None)

    assert ok is True
    assert message == "Volume decreased."


def test_volume_down_boundary_before_equals_after_still_counts_as_success(monkeypatch):
    # Volume was already at zero: before == after. The handler only fails
    # if the volume actually rose, so an unchanged reading is still success.
    monkeypatch.setattr(system_actions, "get_output_volume", lambda: 0)
    monkeypatch.setattr(system_actions, "change_volume", lambda delta: True)

    ok, message, data = _handler("volume_down")(None)

    assert ok is True
    assert message == "Volume decreased."


def test_volume_down_failure_when_change_volume_reports_failure(monkeypatch):
    monkeypatch.setattr(system_actions, "get_output_volume", lambda: 0)
    monkeypatch.setattr(system_actions, "change_volume", lambda delta: False)

    ok, message, data = _handler("volume_down")(None)

    assert ok is False
    assert message == "I couldn't decrease the volume."


# --- mute / unmute ----------------------------------------------------------

def test_mute_success_when_confirmed_muted(monkeypatch):
    monkeypatch.setattr(system_actions, "mute", lambda: True)
    monkeypatch.setattr(system_actions, "is_output_muted", lambda: True)

    ok, message, data = _handler("mute")(None)

    assert ok is True
    assert message == "Muted."


def test_mute_failure_when_still_unmuted(monkeypatch):
    monkeypatch.setattr(system_actions, "mute", lambda: True)
    monkeypatch.setattr(system_actions, "is_output_muted", lambda: False)

    ok, message, data = _handler("mute")(None)

    assert ok is False
    assert message == "I couldn't mute the volume."


def test_unmute_success_when_confirmed_unmuted(monkeypatch):
    monkeypatch.setattr(system_actions, "unmute", lambda: True)
    monkeypatch.setattr(system_actions, "is_output_muted", lambda: False)

    ok, message, data = _handler("unmute")(None)

    assert ok is True
    assert message == "Unmuted."


def test_unmute_failure_when_still_muted(monkeypatch):
    monkeypatch.setattr(system_actions, "unmute", lambda: True)
    monkeypatch.setattr(system_actions, "is_output_muted", lambda: True)

    ok, message, data = _handler("unmute")(None)

    assert ok is False
    assert message == "I couldn't unmute the volume."


# --- lock screen -------------------------------------------------------

def test_lock_screen_success(monkeypatch):
    monkeypatch.setattr(system_actions, "lock_screen", lambda: True)
    ok, message, data = _handler("lock_screen")(None)
    assert ok is True
    assert message == "Locking screen."


def test_lock_screen_failure(monkeypatch):
    monkeypatch.setattr(system_actions, "lock_screen", lambda: False)
    ok, message, data = _handler("lock_screen")(None)
    assert ok is False
    assert message == "I couldn't lock the screen."


# --- battery status ----------------------------------------------------

def test_battery_status_success(monkeypatch):
    monkeypatch.setattr(system_actions, "get_battery_status", lambda: "Battery at 80 percent")
    ok, message, data = _handler("battery_status")(None)
    assert ok is True
    assert message == "Battery at 80 percent"
    assert data == {"status": "Battery at 80 percent"}


def test_battery_status_failure_when_empty(monkeypatch):
    monkeypatch.setattr(system_actions, "get_battery_status", lambda: "")
    ok, message, data = _handler("battery_status")(None)
    assert ok is False
    assert message == "I couldn't get the battery status."
    assert data == {}


# --- clipboard read ----------------------------------------------------

def test_clipboard_read_success(monkeypatch):
    monkeypatch.setattr(system_actions, "read_clipboard", lambda: "hello world")
    ok, message, data = _handler("clipboard_read")(None)
    assert ok is True
    assert message == "Your clipboard contains: hello world"
    assert data == {"content": "hello world"}


def test_clipboard_read_empty_is_failure(monkeypatch):
    monkeypatch.setattr(system_actions, "read_clipboard", lambda: "")
    ok, message, data = _handler("clipboard_read")(None)
    assert ok is False
    assert message == "Your clipboard is empty."


def test_clipboard_read_truncates_long_content(monkeypatch):
    long_content = "x" * 300
    monkeypatch.setattr(system_actions, "read_clipboard", lambda: long_content)
    ok, message, data = _handler("clipboard_read")(None)
    assert ok is True
    assert message == f"Your clipboard contains: {'x' * 200}..."
    assert data == {"content": long_content}


# --- screenshot -------------------------------------------------------

def test_screenshot_success(monkeypatch):
    monkeypatch.setattr(system_actions, "take_screenshot", lambda: "/Users/x/Desktop/shot.png")
    ok, message, data = _handler("screenshot")(None)
    assert ok is True
    assert message == "Screenshot saved to your desktop."
    assert data == {"path": "/Users/x/Desktop/shot.png"}


def test_screenshot_failure_when_no_path(monkeypatch):
    monkeypatch.setattr(system_actions, "take_screenshot", lambda: None)
    ok, message, data = _handler("screenshot")(None)
    assert ok is False
    assert message == "I couldn't take a screenshot."
    assert data == {}


# --- reminder_add / note_add requiring a value -----------------------------

def test_reminder_add_requires_value():
    ok, message, data = _handler("reminder_add")(None)
    assert ok is False
    assert message == "What should I remind you of?"


def test_reminder_add_requires_value_blank_string():
    ok, message, data = _handler("reminder_add")("   ")
    assert ok is False
    assert message == "What should I remind you of?"


def test_reminder_add_success(monkeypatch):
    monkeypatch.setattr(system_actions, "add_reminder", lambda text: True)
    ok, message, data = _handler("reminder_add")("call mom at 5pm")
    assert ok is True
    assert message == "Reminder added: call mom at 5pm."
    assert data == {"text": "call mom at 5pm"}


def test_reminder_add_failure(monkeypatch):
    monkeypatch.setattr(system_actions, "add_reminder", lambda text: False)
    ok, message, data = _handler("reminder_add")("call mom")
    assert ok is False
    assert message == "I couldn't add that reminder."
    assert data == {}


def test_note_add_requires_value():
    ok, message, data = _handler("note_add")(None)
    assert ok is False
    assert message == "What should the note say?"


def test_note_add_success(monkeypatch):
    monkeypatch.setattr(system_actions, "add_note", lambda text: True)
    ok, message, data = _handler("note_add")("buy milk")
    assert ok is True
    assert message == "Note added."
    assert data == {"text": "buy milk"}


def test_note_add_failure(monkeypatch):
    monkeypatch.setattr(system_actions, "add_note", lambda text: False)
    ok, message, data = _handler("note_add")("buy milk")
    assert ok is False
    assert message == "I couldn't add that note."


# --- registry sanity -----------------------------------------------------

def test_system_actions_pipe_list_contains_all_registered_actions():
    for name in system_actions.SYSTEM_ACTIONS:
        assert name in system_actions.SYSTEM_ACTIONS_PIPE_LIST.split("|")


def test_reminder_and_note_actions_require_value_flag():
    assert system_actions.SYSTEM_ACTIONS["reminder_add"].requires_value is True
    assert system_actions.SYSTEM_ACTIONS["note_add"].requires_value is True
    assert system_actions.SYSTEM_ACTIONS["volume_up"].requires_value is False
