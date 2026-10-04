import core.executor as executor


def _silence(monkeypatch):
    monkeypatch.setattr(executor, "save_action", lambda *a, **k: None)
    monkeypatch.setattr(executor, "set_last_song", lambda *a, **k: None)
    monkeypatch.setattr(executor, "set_last_app", lambda *a, **k: None)
    monkeypatch.setattr(executor, "set_last_browser_target", lambda *a, **k: None)
    monkeypatch.setattr(executor, "set_last_shortcut", lambda *a, **k: None)
    monkeypatch.setattr(executor, "set_last_action", lambda *a, **k: None)


def _capture_save_action(monkeypatch):
    calls = []
    monkeypatch.setattr(
        executor, "save_action",
        lambda **kwargs: calls.append(kwargs),
    )
    return calls


# --- app branch ---------------------------------------------------------

def test_execute_app_success_sets_memory_and_logs(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "open_app", lambda name: True)
    monkeypatch.setattr(executor, "is_app_running", lambda name: True)

    set_app_calls = []
    set_action_calls = []
    monkeypatch.setattr(executor, "set_last_app", lambda name: set_app_calls.append(name))
    monkeypatch.setattr(executor, "set_last_action", lambda t, v: set_action_calls.append((t, v)))
    save_calls = _capture_save_action(monkeypatch)

    result = executor.execute({"tool": "app", "name": "Safari"}, "open safari")

    assert result == {
        "ok": True,
        "message": "Opening Safari.",
        "code": "app_opened",
        "action_type": "app",
        "retryable": False,
        "data": {"name": "Safari"},
    }
    assert set_app_calls == ["Safari"]
    assert set_action_calls == [("app", "Safari")]
    assert len(save_calls) == 1
    assert save_calls[0]["action_type"] == "app"
    assert save_calls[0]["result"] == "success"


def test_execute_app_missing_name_returns_failure_without_launch(monkeypatch):
    _silence(monkeypatch)

    def fail_if_called(*a, **k):
        raise AssertionError("open_app should not be called without a name")

    monkeypatch.setattr(executor, "open_app", fail_if_called)

    result = executor.execute({"tool": "app", "name": ""}, "open")

    assert result == {
        "ok": False,
        "message": "I couldn't figure out which app to open.",
        "code": "app_missing_name",
        "action_type": "app",
        "retryable": False,
        "data": {},
    }


def test_execute_app_launch_ok_but_not_verified_is_failure(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "open_app", lambda name: True)
    monkeypatch.setattr(executor, "is_app_running", lambda name: False)

    result = executor.execute({"tool": "app", "name": "GhostApp"}, "open ghostapp")

    assert result["ok"] is False
    assert result["code"] == "app_open_failed"
    assert result["retryable"] is True


# --- music branch --------------------------------------------------------

def test_execute_music_success(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "play_music_any", lambda query: True)
    save_calls = _capture_save_action(monkeypatch)

    result = executor.execute({"tool": "music", "query": "Starboy"}, "play Starboy")

    assert result == {
        "ok": True,
        "message": "Playing Starboy.",
        "code": "music_playing",
        "action_type": "music",
        "retryable": False,
        "data": {"query": "Starboy"},
    }
    assert save_calls[0]["action_type"] == "music"


def test_execute_music_missing_query(monkeypatch):
    _silence(monkeypatch)
    result = executor.execute({"tool": "music", "query": ""}, "play")
    assert result["ok"] is False
    assert result["code"] == "music_missing_query"


def test_execute_music_play_failure_is_retryable(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "play_music_any", lambda query: False)

    result = executor.execute({"tool": "music", "query": "Starboy"}, "play Starboy")

    assert result["ok"] is False
    assert result["code"] == "music_play_failed"
    assert result["retryable"] is True


# --- shortcut branch ------------------------------------------------------

def test_execute_shortcut_success(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "run_shortcut", lambda name: True)

    result = executor.execute({"tool": "shortcut", "name": "Good Morning"}, "run good morning")

    assert result == {
        "ok": True,
        "message": "Done.",
        "code": "shortcut_ran",
        "action_type": "shortcut",
        "retryable": False,
        "data": {"name": "Good Morning"},
    }


def test_execute_shortcut_missing_name(monkeypatch):
    _silence(monkeypatch)
    result = executor.execute({"tool": "shortcut", "name": ""}, "run shortcut")
    assert result["ok"] is False
    assert result["code"] == "shortcut_missing_name"


def test_execute_shortcut_failure(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "run_shortcut", lambda name: False)
    result = executor.execute({"tool": "shortcut", "name": "Broken"}, "run broken")
    assert result["ok"] is False
    assert result["code"] == "shortcut_failed"
    assert result["retryable"] is True


# --- browser branch -------------------------------------------------------

def test_execute_browser_success_without_query(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "open_target", lambda target, query=None: True)

    result = executor.execute({"tool": "browser", "target": "youtube"}, "open youtube")

    assert result == {
        "ok": True,
        "message": "Opening youtube.",
        "code": "browser_opened",
        "action_type": "browser",
        "retryable": False,
        "data": {"target": "youtube"},
    }


def test_execute_browser_success_with_query(monkeypatch):
    _silence(monkeypatch)
    captured = {}

    def fake_open_target(target, query=None):
        captured["target"] = target
        captured["query"] = query
        return True

    monkeypatch.setattr(executor, "open_target", fake_open_target)

    result = executor.execute(
        {"tool": "browser", "target": "youtube", "query": "ai news"}, "search youtube for ai news"
    )

    assert captured == {"target": "youtube", "query": "ai news"}
    assert result["ok"] is True
    assert result["code"] == "browser_open_and_search_ok"
    assert result["data"] == {"target": "youtube", "query": "ai news"}


def test_execute_browser_missing_target(monkeypatch):
    _silence(monkeypatch)
    result = executor.execute({"tool": "browser", "target": ""}, "open")
    assert result["ok"] is False
    assert result["code"] == "browser_missing_target"


def test_execute_browser_search_failure_is_not_retryable(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "open_target", lambda target, query=None: False)

    result = executor.execute(
        {"tool": "browser", "target": "youtube", "query": "ai news"}, "search youtube for ai news"
    )

    assert result["ok"] is False
    assert result["code"] == "browser_site_search_blocked_or_failed"
    assert result["retryable"] is False


# --- open branch ----------------------------------------------------------

def test_execute_open_success(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "open_target", lambda target, query=None: True)

    result = executor.execute({"tool": "open", "target": "myfile.pdf"}, "open myfile.pdf")

    assert result == {
        "ok": True,
        "message": "Opening myfile.pdf.",
        "code": "open_target_opened",
        "action_type": "open",
        "retryable": False,
        "data": {"target": "myfile.pdf"},
    }


def test_execute_open_missing_target(monkeypatch):
    _silence(monkeypatch)
    result = executor.execute({"tool": "open", "target": ""}, "open")
    assert result["ok"] is False
    assert result["code"] == "open_missing_target"


def test_execute_open_failure_is_retryable(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "open_target", lambda target, query=None: False)
    result = executor.execute({"tool": "open", "target": "myfile.pdf"}, "open myfile.pdf")
    assert result["ok"] is False
    assert result["code"] == "open_target_failed"
    assert result["retryable"] is True


# --- system branch ---------------------------------------------------------

def test_execute_system_dispatches_to_registered_handler(monkeypatch):
    _silence(monkeypatch)

    calls = []

    class FakeSpec:
        def handler(self, value):
            calls.append(value)
            return True, "Volume increased.", {}

    monkeypatch.setattr(executor, "SYSTEM_ACTIONS", {"volume_up": FakeSpec()})

    set_action_calls = []
    monkeypatch.setattr(executor, "set_last_action", lambda t, v: set_action_calls.append((t, v)))

    result = executor.execute({"tool": "system", "action": "volume_up"}, "turn up the volume")

    assert result == {
        "ok": True,
        "message": "Volume increased.",
        "code": "system_volume_up_ok",
        "action_type": "system",
        "retryable": False,
        "data": {},
    }
    assert calls == [None]
    assert set_action_calls == [("system", "volume_up")]


def test_execute_system_unknown_action(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(executor, "SYSTEM_ACTIONS", {})

    result = executor.execute({"tool": "system", "action": "teleport"}, "teleport me")

    assert result["ok"] is False
    assert result["code"] == "system_unknown_action"


def test_execute_system_handler_failure_does_not_set_memory(monkeypatch):
    _silence(monkeypatch)

    class FakeSpec:
        def handler(self, value):
            return False, "I couldn't mute the volume.", {}

    monkeypatch.setattr(executor, "SYSTEM_ACTIONS", {"mute": FakeSpec()})

    def fail_if_called(*a, **k):
        raise AssertionError("set_last_action should not be called on failure")

    monkeypatch.setattr(executor, "set_last_action", fail_if_called)

    result = executor.execute({"tool": "system", "action": "mute"}, "mute")

    assert result["ok"] is False
    assert result["code"] == "system_mute_failed"


# --- brain / unhandled branch ----------------------------------------------

def test_execute_brain_response_logs_success(monkeypatch):
    _silence(monkeypatch)
    save_calls = _capture_save_action(monkeypatch)

    result = executor.execute({"tool": None, "response": "It's sunny today."}, "how's the weather")

    assert result == {
        "ok": True,
        "message": "It's sunny today.",
        "code": "brain_response",
        "action_type": "brain",
        "retryable": False,
        "data": {},
    }
    assert save_calls[0]["action_type"] == "brain"
    assert save_calls[0]["result"] == "success"


def test_execute_unhandled_response_logs_failure(monkeypatch):
    _silence(monkeypatch)
    save_calls = _capture_save_action(monkeypatch)

    result = executor.execute(
        {"tool": None, "response": "I don't remember.", "_unhandled_reason": "music_memory_missing"},
        "play that again",
    )

    assert result == {
        "ok": False,
        "message": "I don't remember.",
        "code": "unhandled_music_memory_missing",
        "action_type": "unknown",
        "retryable": False,
        "data": {},
    }
    assert save_calls[0]["action_type"] == "unhandled"
    assert save_calls[0]["result"] == "failure"


def test_execute_unknown_decision_logs_failure(monkeypatch):
    _silence(monkeypatch)
    save_calls = _capture_save_action(monkeypatch)

    result = executor.execute({"tool": None, "response": ""}, "gibberish")

    assert result["ok"] is False
    assert result["code"] == "unknown_decision"
    assert save_calls[0]["action_type"] == "unhandled"
