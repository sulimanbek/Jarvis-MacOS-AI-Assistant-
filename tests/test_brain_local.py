import core.brain_local as bl


def _clear_state(monkeypatch):
    monkeypatch.setattr(bl, "get_last_song", lambda: None)
    monkeypatch.setattr(bl, "get_last_app", lambda: None)
    monkeypatch.setattr(bl, "get_last_browser_target", lambda: None)
    monkeypatch.setattr(bl, "get_last_shortcut", lambda: None)
    monkeypatch.setattr(bl, "get_last_action", lambda: {})


def test_build_state_block_empty_when_no_state(monkeypatch):
    _clear_state(monkeypatch)

    assert bl._build_state_block() == ""


def test_build_state_block_includes_present_fields_only(monkeypatch):
    _clear_state(monkeypatch)
    monkeypatch.setattr(bl, "get_last_song", lambda: "Starboy")
    monkeypatch.setattr(bl, "get_last_app", lambda: "Safari")
    monkeypatch.setattr(bl, "get_last_action", lambda: {"type": "music", "value": "Starboy"})

    block = bl._build_state_block()

    assert "last song played: Starboy" in block
    assert "last app opened: Safari" in block
    assert "last action: music -> Starboy" in block
    # Fields with no known value must not appear
    assert "browser target" not in block
    assert "shortcut" not in block


def test_build_history_messages_excludes_current_turn(monkeypatch):
    monkeypatch.setattr(bl, "get_last_messages", lambda: [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "hi there"},
        {"role": "user", "text": "play some music"},
    ])

    history = bl._build_history_messages("play some music")

    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_build_history_messages_keeps_current_turn_if_not_last(monkeypatch):
    # Current utterance isn't the trailing entry -> nothing gets dropped
    monkeypatch.setattr(bl, "get_last_messages", lambda: [
        {"role": "user", "text": "play some music"},
        {"role": "assistant", "text": "playing now"},
    ])

    history = bl._build_history_messages("play some music")

    assert history == [
        {"role": "user", "content": "play some music"},
        {"role": "assistant", "content": "playing now"},
    ]


def test_build_history_messages_trims_to_max_turns(monkeypatch):
    messages = [{"role": "user", "text": f"msg {i}"} for i in range(20)]
    monkeypatch.setattr(bl, "get_last_messages", lambda: messages)

    history = bl._build_history_messages("not the trailing message")

    assert len(history) == bl.MAX_CONTEXT_TURNS
    assert history[-1]["content"] == "msg 19"


def test_build_history_messages_drops_empty_and_unknown_roles(monkeypatch):
    monkeypatch.setattr(bl, "get_last_messages", lambda: [
        {"role": "user", "text": ""},
        {"role": "system", "text": "should be dropped"},
        {"role": "assistant", "text": "kept"},
    ])

    history = bl._build_history_messages("current")

    assert history == [{"role": "assistant", "content": "kept"}]


def test_think_local_injects_state_block_and_history(monkeypatch):
    _clear_state(monkeypatch)
    monkeypatch.setattr(bl, "get_last_app", lambda: "Safari")
    monkeypatch.setattr(bl, "get_last_messages", lambda: [
        {"role": "user", "text": "earlier message"},
        {"role": "user", "text": "open safari again"},
    ])

    captured = {}

    def fake_ask_ollama(messages, model):
        captured["messages"] = messages
        return '{"tool": "app", "name": "Safari"}'

    monkeypatch.setattr(bl, "ask_ollama", fake_ask_ollama)

    result = bl.think_local("open safari again")

    assert result == {"tool": "app", "name": "Safari"}
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert "last app opened: Safari" in messages[0]["content"]
    assert {"role": "user", "content": "earlier message"} in messages
    assert messages[-1] == {"role": "user", "content": "open safari again"}


def test_think_with_system_without_context_ignores_history(monkeypatch):
    monkeypatch.setattr(bl, "get_last_messages", lambda: [
        {"role": "user", "text": "should not appear"},
    ])

    captured = {}

    def fake_ask_ollama(messages, model):
        captured["messages"] = messages
        return "raw response"

    monkeypatch.setattr(bl, "ask_ollama", fake_ask_ollama)

    bl.think_with_system("hello", "SYSTEM PROMPT")

    messages = captured["messages"]
    assert messages == [
        {"role": "system", "content": "SYSTEM PROMPT"},
        {"role": "user", "content": "hello"},
    ]


def test_think_local_handles_json_array_response_gracefully(monkeypatch):
    # A technically-valid JSON payload that isn't a dict (e.g. the local LLM
    # returning a bare list) must not crash think_local's callers.
    _clear_state(monkeypatch)
    monkeypatch.setattr(bl, "ask_ollama", lambda messages, model: "[1, 2, 3]")

    result = bl.think_local("do something ambiguous")

    assert result == {"tool": None, "response": "I had trouble understanding that."}


def test_think_local_handles_ollama_returning_nothing(monkeypatch):
    _clear_state(monkeypatch)
    monkeypatch.setattr(bl, "ask_ollama", lambda messages, model: None)

    result = bl.think_local("open safari")

    assert result == {
        "tool": None,
        "response": "I'm having trouble connecting to my local model right now.",
    }
