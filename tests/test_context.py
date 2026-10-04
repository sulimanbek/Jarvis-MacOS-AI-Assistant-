import json

import memory.context as context


def _redirect(monkeypatch, tmp_path):
    path = tmp_path / "context.json"
    monkeypatch.setattr(context, "CONTEXT_FILE_PATH", str(path))
    return path


def test_add_message_and_get_last_messages_round_trip(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    context.add_message("user", "hello")
    context.add_message("assistant", "hi there")

    messages = context.get_last_messages()

    assert messages == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "hi there"},
    ]


def test_get_last_user_message_returns_most_recent_user_text(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    context.add_message("user", "first")
    context.add_message("assistant", "reply")
    context.add_message("user", "second")

    assert context.get_last_user_message() == "second"


def test_get_last_user_message_returns_none_when_no_user_messages(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    context.add_message("assistant", "only assistant")

    assert context.get_last_user_message() is None


def test_add_message_trims_history_to_max_history(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    for i in range(context.MAX_HISTORY + 5):
        context.add_message("user", f"msg {i}")

    messages = context.get_last_messages()

    assert len(messages) == context.MAX_HISTORY
    assert messages[0]["text"] == "msg 5"
    assert messages[-1]["text"] == f"msg {context.MAX_HISTORY + 4}"


def test_set_get_last_song_round_trip(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert context.get_last_song() is None
    context.set_last_song("Starboy")
    assert context.get_last_song() == "Starboy"


def test_set_get_last_app_round_trip(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert context.get_last_app() is None
    context.set_last_app("Safari")
    assert context.get_last_app() == "Safari"


def test_set_get_last_browser_target_round_trip(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert context.get_last_browser_target() is None
    context.set_last_browser_target("github.com")
    assert context.get_last_browser_target() == "github.com"


def test_set_get_last_shortcut_round_trip(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert context.get_last_shortcut() is None
    context.set_last_shortcut("Good Morning")
    assert context.get_last_shortcut() == "Good Morning"


def test_set_get_last_action_round_trip(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert context.get_last_action() == {}
    context.set_last_action("music", "Starboy")
    assert context.get_last_action() == {"type": "music", "value": "Starboy"}


def test_safe_read_does_not_raise_on_missing_file(monkeypatch, tmp_path):
    path = _redirect(monkeypatch, tmp_path)
    assert not path.exists()

    data = context._safe_read()

    assert data == {"messages": [], "state": {}}
    assert path.exists()


def test_safe_read_does_not_raise_on_corrupt_file_and_resets(monkeypatch, tmp_path):
    path = _redirect(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    data = context._safe_read()

    assert data == {"messages": [], "state": {}}


def test_safe_write_does_not_raise_when_directory_missing(monkeypatch, tmp_path):
    # Point CONTEXT_FILE_PATH at a path whose parent directory doesn't exist,
    # so the os.replace inside _safe_write fails — characterize the existing
    # silent-failure behavior (it must not raise).
    bad_path = tmp_path / "nonexistent_dir" / "context.json"
    monkeypatch.setattr(context, "CONTEXT_FILE_PATH", str(bad_path))

    context._safe_write({"messages": [], "state": {}})  # must not raise


def test_upgrades_legacy_list_format_to_dict(monkeypatch, tmp_path):
    path = _redirect(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = [{"role": "user", "text": "old format"}]
    path.write_text(json.dumps(legacy), encoding="utf-8")

    data = context._safe_read()

    assert data == {"messages": [{"role": "user", "text": "old format"}], "state": {}}
