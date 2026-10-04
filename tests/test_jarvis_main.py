import jarvis


class _FakeAudio:
    """Minimal stand-in for a numpy array with a .size attribute."""

    def __init__(self, size):
        self.size = size


def _silence(monkeypatch):
    monkeypatch.setattr(jarvis, "speak", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "save_action", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "add_message", lambda *a, **k: None)


# ── _run_startup_health_checks ────────────────────────────────────────────

def _mock_all_healthy(monkeypatch):
    monkeypatch.setattr(jarvis.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(jarvis.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(jarvis, "is_ollama_running", lambda: True)


def test_run_startup_health_checks_all_healthy_returns_no_errors_or_warnings(monkeypatch):
    _mock_all_healthy(monkeypatch)

    errors, warnings = jarvis._run_startup_health_checks()

    assert errors == []
    assert warnings == []


def test_run_startup_health_checks_missing_binaries_reports_errors(monkeypatch):
    monkeypatch.setattr(jarvis.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(jarvis.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(jarvis, "is_ollama_running", lambda: False)

    errors, warnings = jarvis._run_startup_health_checks()

    assert any("Whisper binary" in e for e in errors)
    assert any("Whisper model" in e for e in errors)
    assert any("say" in e for e in errors)
    assert any("osascript" in e for e in errors)
    assert any("Shortcuts CLI" in w for w in warnings)
    assert any("Ollama" in w for w in warnings)


def test_run_startup_health_checks_missing_shortcuts_only_warns(monkeypatch):
    monkeypatch.setattr(jarvis.os.path, "isfile", lambda path: True)

    def fake_which(cmd):
        return None if cmd == "shortcuts" else f"/usr/bin/{cmd}"

    monkeypatch.setattr(jarvis.shutil, "which", fake_which)
    monkeypatch.setattr(jarvis, "is_ollama_running", lambda: True)

    errors, warnings = jarvis._run_startup_health_checks()

    assert errors == []
    assert any("Shortcuts CLI" in w for w in warnings)


# ── _listen_once_for_confirmation ─────────────────────────────────────────

def test_listen_once_for_confirmation_returns_empty_on_empty_audio(monkeypatch):
    monkeypatch.setattr(jarvis, "record_push_to_talk", lambda: (_FakeAudio(0), 16000))

    assert jarvis._listen_once_for_confirmation() == ""


def test_listen_once_for_confirmation_returns_lowered_stripped_transcript(monkeypatch):
    monkeypatch.setattr(jarvis, "record_push_to_talk", lambda: (_FakeAudio(10), 16000))
    monkeypatch.setattr(jarvis, "transcribe", lambda audio, sr: "  YES Please  ")

    assert jarvis._listen_once_for_confirmation() == "yes please"


def test_listen_once_for_confirmation_returns_empty_on_transcribe_exception(monkeypatch):
    monkeypatch.setattr(jarvis, "record_push_to_talk", lambda: (_FakeAudio(10), 16000))

    def raise_error(audio, sr):
        raise RuntimeError("boom")

    monkeypatch.setattr(jarvis, "transcribe", raise_error)

    assert jarvis._listen_once_for_confirmation() == ""


# ── _requires_confirmation ─────────────────────────────────────────────────

def test_requires_confirmation_delegates_to_policy_with_tool_name(monkeypatch):
    captured = {}

    def fake_policy_requires_confirmation(tool):
        captured["tool"] = tool
        return True

    monkeypatch.setattr(jarvis, "_policy_requires_confirmation", fake_policy_requires_confirmation)

    result = jarvis._requires_confirmation({"tool": "shortcut", "name": "DoThing"})

    assert result is True
    assert captured["tool"] == "shortcut"


def test_requires_confirmation_false_when_policy_says_no(monkeypatch):
    monkeypatch.setattr(jarvis, "_policy_requires_confirmation", lambda tool: False)

    assert jarvis._requires_confirmation({"tool": "music"}) is False


# ── _confirm_action ─────────────────────────────────────────────────────────

def test_confirm_action_returns_true_on_yes(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(jarvis, "_listen_once_for_confirmation", lambda: "yes go ahead")

    assert jarvis._confirm_action({"tool": "shortcut"}) is True


def test_confirm_action_returns_false_on_no(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(jarvis, "_listen_once_for_confirmation", lambda: "no cancel")

    assert jarvis._confirm_action({"tool": "shortcut"}) is False


def test_confirm_action_returns_false_on_unintelligible_response(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(jarvis, "_listen_once_for_confirmation", lambda: "banana pancakes")

    assert jarvis._confirm_action({"tool": "shortcut"}) is False


def test_confirm_action_returns_false_when_nothing_heard(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(jarvis, "_listen_once_for_confirmation", lambda: "")

    assert jarvis._confirm_action({"tool": "shortcut"}) is False


# ── main() loop behavior (limited) ──────────────────────────────────────────

def _pass_health_checks(monkeypatch):
    monkeypatch.setattr(jarvis, "_run_startup_health_checks", lambda: ([], []))
    monkeypatch.setattr(jarvis, "ensure_ollama_running", lambda: True)


def test_main_exits_cleanly_on_keyboard_interrupt(monkeypatch):
    _silence(monkeypatch)
    _pass_health_checks(monkeypatch)

    def raise_interrupt():
        raise KeyboardInterrupt()

    monkeypatch.setattr(jarvis, "record_push_to_talk", raise_interrupt)

    # Should not propagate
    jarvis.main()


def test_main_processes_exit_command_then_stops(monkeypatch):
    _silence(monkeypatch)
    _pass_health_checks(monkeypatch)

    calls = {"n": 0}

    def fake_record_push_to_talk():
        calls["n"] += 1
        if calls["n"] == 1:
            return (_FakeAudio(10), 16000)
        # Safety net in case the loop doesn't exit as expected.
        raise KeyboardInterrupt()

    monkeypatch.setattr(jarvis, "record_push_to_talk", fake_record_push_to_talk)
    monkeypatch.setattr(jarvis, "transcribe", lambda audio, sr: "goodbye")

    def fail_route(user_text):
        raise AssertionError("route should not be called for an exit command")

    monkeypatch.setattr(jarvis, "route", fail_route)

    jarvis.main()

    assert calls["n"] == 1


def test_main_does_not_propagate_startup_health_error(monkeypatch):
    _silence(monkeypatch)
    monkeypatch.setattr(jarvis, "_run_startup_health_checks", lambda: (["bad"], []))

    def fail_record(*a, **k):
        raise AssertionError("should not attempt to record when startup errors exist")

    monkeypatch.setattr(jarvis, "record_push_to_talk", fail_record)

    jarvis.main()
