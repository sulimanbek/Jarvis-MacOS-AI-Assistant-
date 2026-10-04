import daemon


class _FakeAudio:
    """Minimal stand-in for a numpy array with a .size attribute."""

    def __init__(self, size):
        self.size = size


class _FakeListener:
    """Stand-in for ContinuousListener; feeds a scripted sequence of
    (audio, sr) tuples or exceptions on successive listen_for_command() calls."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0
        self.stopped = False

    def listen_for_command(self):
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def stop(self):
        self.stopped = True


def _silence(monkeypatch):
    monkeypatch.setattr(daemon, "speak", lambda *a, **k: None)
    monkeypatch.setattr(daemon, "speak_ack", lambda *a, **k: None)
    monkeypatch.setattr(daemon, "save_action", lambda *a, **k: None)
    monkeypatch.setattr(daemon, "add_message", lambda *a, **k: None)


# ── _startup_checks ─────────────────────────────────────────────────────────

def test_startup_checks_all_healthy_returns_no_errors_or_warnings(monkeypatch):
    monkeypatch.setattr(daemon.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(daemon.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(daemon, "is_ollama_running", lambda: True)

    errors, warnings = daemon._startup_checks()

    assert errors == []
    assert warnings == []


def test_startup_checks_missing_binaries_reports_errors_and_ollama_warning(monkeypatch):
    monkeypatch.setattr(daemon.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(daemon.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(daemon, "is_ollama_running", lambda: False)

    errors, warnings = daemon._startup_checks()

    assert any("Whisper binary" in e for e in errors)
    assert any("Whisper model" in e for e in errors)
    assert any("say" in e for e in errors)
    assert any("osascript" in e for e in errors)
    assert any("Ollama" in w for w in warnings)


# ── _requires_confirmation ───────────────────────────────────────────────────

def test_requires_confirmation_delegates_to_policy_with_tool_name(monkeypatch):
    captured = {}

    def fake_policy_requires_confirmation(tool):
        captured["tool"] = tool
        return True

    monkeypatch.setattr(daemon, "_policy_requires_confirmation", fake_policy_requires_confirmation)

    result = daemon._requires_confirmation({"tool": "shortcut", "name": "DoThing"})

    assert result is True
    assert captured["tool"] == "shortcut"


def test_requires_confirmation_false_when_policy_says_no(monkeypatch):
    monkeypatch.setattr(daemon, "_policy_requires_confirmation", lambda tool: False)

    assert daemon._requires_confirmation({"tool": "music"}) is False


# ── _confirm_action ──────────────────────────────────────────────────────────

def test_confirm_action_returns_true_on_yes(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([(_FakeAudio(10), 16000)])
    monkeypatch.setattr(daemon, "transcribe", lambda audio, sr: "yes go ahead")

    assert daemon._confirm_action(listener, {"tool": "shortcut"}) is True


def test_confirm_action_returns_false_on_no(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([(_FakeAudio(10), 16000)])
    monkeypatch.setattr(daemon, "transcribe", lambda audio, sr: "no cancel")

    assert daemon._confirm_action(listener, {"tool": "shortcut"}) is False


def test_confirm_action_returns_false_on_unintelligible_response(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([(_FakeAudio(10), 16000)])
    monkeypatch.setattr(daemon, "transcribe", lambda audio, sr: "banana pancakes")

    assert daemon._confirm_action(listener, {"tool": "shortcut"}) is False


def test_confirm_action_returns_false_when_no_audio_captured(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([(_FakeAudio(0), 16000)])

    def fail_transcribe(*a, **k):
        raise AssertionError("transcribe should not be called with empty audio")

    monkeypatch.setattr(daemon, "transcribe", fail_transcribe)

    assert daemon._confirm_action(listener, {"tool": "shortcut"}) is False


def test_confirm_action_returns_false_on_transcribe_exception(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([(_FakeAudio(10), 16000)])

    def raise_error(audio, sr):
        raise RuntimeError("boom")

    monkeypatch.setattr(daemon, "transcribe", raise_error)

    assert daemon._confirm_action(listener, {"tool": "shortcut"}) is False


# ── _process_command ─────────────────────────────────────────────────────────

def test_process_command_exit_command_returns_exit_and_speaks_goodbye(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    spoken = []
    monkeypatch.setattr(daemon, "speak", lambda msg: spoken.append(msg))

    def fail_route(user_text):
        raise AssertionError("route should not be called for an exit command")

    monkeypatch.setattr(daemon, "route", fail_route)

    result = daemon._process_command("goodbye", listener)

    assert result == "exit"
    assert any("Goodbye" in m for m in spoken)


def test_process_command_routing_exception_is_handled(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])

    def raise_error(user_text):
        raise RuntimeError("routing broke")

    monkeypatch.setattr(daemon, "route", raise_error)

    logged = {}

    def fake_save_action(action_type, user_input, result, details):
        logged.update(action_type=action_type, user_input=user_input, result=result, details=details)

    monkeypatch.setattr(daemon, "save_action", fake_save_action)

    result = daemon._process_command("do something weird", listener)

    assert result is None
    assert logged["action_type"] == "routing"
    assert logged["result"] == "failure"


def test_process_command_agent_path_passes_callable_confirm_step(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "__agent__"})

    captured = {}

    def fake_run_agent(user_text, confirm_step=None):
        captured["confirm_step"] = confirm_step
        return {"ok": True, "message": "all done"}

    monkeypatch.setattr(daemon, "run_agent", fake_run_agent)

    result = daemon._process_command("open safari and then play music", listener)

    assert result is None
    assert callable(captured["confirm_step"])


def test_process_command_agent_confirm_step_allows_when_no_confirmation_required(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "__agent__"})
    monkeypatch.setattr(daemon, "_requires_confirmation", lambda step: False)

    def fail_confirm_action(*a, **k):
        raise AssertionError("_confirm_action should not be called when confirmation isn't required")

    monkeypatch.setattr(daemon, "_confirm_action", fail_confirm_action)

    captured = {}

    def fake_run_agent(user_text, confirm_step=None):
        captured["confirm_step"] = confirm_step
        return {"ok": True, "message": "done"}

    monkeypatch.setattr(daemon, "run_agent", fake_run_agent)

    daemon._process_command("open safari and then play music", listener)

    assert captured["confirm_step"]({"tool": "app", "name": "Safari"}) is True


def test_process_command_agent_confirm_step_can_deny_a_step(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "__agent__"})
    monkeypatch.setattr(daemon, "_requires_confirmation", lambda step: True)
    monkeypatch.setattr(daemon, "_confirm_action", lambda listener, step: False)

    logged = []
    monkeypatch.setattr(
        daemon, "save_action",
        lambda action_type, user_input, result, details: logged.append((action_type, result, details)),
    )

    captured = {}

    def fake_run_agent(user_text, confirm_step=None):
        captured["confirm_step"] = confirm_step
        return {"ok": True, "message": "done"}

    monkeypatch.setattr(daemon, "run_agent", fake_run_agent)

    daemon._process_command("shut down my mac", listener)

    denied = captured["confirm_step"]({"tool": "shortcut", "name": "ShutItDown"})

    assert denied is False
    assert any(entry[0] == "security" and entry[1] == "failure" for entry in logged)


def test_process_command_agent_confirm_step_allows_when_confirmed(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "__agent__"})
    monkeypatch.setattr(daemon, "_requires_confirmation", lambda step: True)
    monkeypatch.setattr(daemon, "_confirm_action", lambda listener, step: True)

    captured = {}

    def fake_run_agent(user_text, confirm_step=None):
        captured["confirm_step"] = confirm_step
        return {"ok": True, "message": "done"}

    monkeypatch.setattr(daemon, "run_agent", fake_run_agent)

    daemon._process_command("run a shortcut", listener)

    assert captured["confirm_step"]({"tool": "shortcut", "name": "DoThing"}) is True


def test_process_command_confirmation_gate_denied_skips_execution(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "shortcut", "name": "DoThing"})
    monkeypatch.setattr(daemon, "_requires_confirmation", lambda step: True)
    monkeypatch.setattr(daemon, "_confirm_action", lambda listener, step: False)

    def fail_execute(*a, **k):
        raise AssertionError("execute should not be called when confirmation is denied")

    monkeypatch.setattr(daemon, "execute", fail_execute)

    logged = []
    monkeypatch.setattr(
        daemon, "save_action",
        lambda action_type, user_input, result, details: logged.append((action_type, result)),
    )

    result = daemon._process_command("run the shortcut", listener)

    assert result is None
    assert ("security", "failure") in logged


def test_process_command_successful_execution_speaks_response(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "app", "name": "Safari"})
    monkeypatch.setattr(daemon, "_requires_confirmation", lambda step: False)
    monkeypatch.setattr(daemon, "execute", lambda decision, user_text: {"ok": True, "message": "Opened Safari"})

    spoken = []
    monkeypatch.setattr(daemon, "speak", lambda msg: spoken.append(msg))

    result = daemon._process_command("open safari", listener)

    assert result is None
    assert "Opened Safari" in spoken


def test_process_command_retries_once_on_retryable_failure(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "app", "name": "Safari"})
    monkeypatch.setattr(daemon, "_requires_confirmation", lambda step: False)

    calls = {"n": 0}

    def fake_execute(decision, user_text):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "message": "transient failure", "retryable": True}
        return {"ok": True, "message": "Opened Safari on retry"}

    monkeypatch.setattr(daemon, "execute", fake_execute)

    spoken = []
    monkeypatch.setattr(daemon, "speak", lambda msg: spoken.append(msg))

    daemon._process_command("open safari", listener)

    assert calls["n"] == 2
    assert "Opened Safari on retry" in spoken


def test_process_command_execution_exception_is_handled(monkeypatch):
    _silence(monkeypatch)
    listener = _FakeListener([])
    monkeypatch.setattr(daemon, "route", lambda user_text: {"tool": "app", "name": "Safari"})
    monkeypatch.setattr(daemon, "_requires_confirmation", lambda step: False)

    def raise_error(decision, user_text):
        raise RuntimeError("execution broke")

    monkeypatch.setattr(daemon, "execute", raise_error)

    logged = []
    monkeypatch.setattr(
        daemon, "save_action",
        lambda action_type, user_input, result, details: logged.append((action_type, result)),
    )

    result = daemon._process_command("open safari", listener)

    assert result is None
    assert ("execution", "failure") in logged


# ── main() per-iteration catch-all ──────────────────────────────────────────
#
# main() has a new per-iteration try/except wrapping the whole loop body.
# We drive it end-to-end here: the fake listener raises a plain Exception on
# its first listen_for_command() call (which main() must catch, log via
# save_action, and continue from), then raises KeyboardInterrupt on the
# second call so the loop exits cleanly. This exercises the real main()
# rather than a smaller unit, so we stub every external dependency it touches.

def test_main_catches_per_iteration_exception_then_exits_on_keyboard_interrupt(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(daemon, "_startup_checks", lambda: ([], []))
    monkeypatch.setattr(daemon, "ensure_ollama_running", lambda: True)

    listener = _FakeListener([RuntimeError("listener blew up"), KeyboardInterrupt()])
    monkeypatch.setattr(daemon, "ContinuousListener", lambda: listener)

    logged = []
    monkeypatch.setattr(
        daemon, "save_action",
        lambda action_type, user_input, result, details: logged.append((action_type, result)),
    )

    # Should not propagate the RuntimeError, and should exit cleanly on
    # KeyboardInterrupt rather than propagating that either.
    daemon.main()

    assert listener.calls == 2
    assert ("system", "failure") in logged
    assert listener.stopped is True
