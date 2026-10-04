import subprocess

import core.verifier as verifier

# --- non-app tools trust the executor result --------------------------

def test_verify_step_trusts_executor_result_for_non_app_tool_success(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("subprocess.run should not be called for non-app tools")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    result = verifier.verify_step({"tool": "music", "query": "Starboy"}, {"ok": True})

    assert result is True


def test_verify_step_returns_false_when_executor_result_not_ok(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("subprocess.run should not be called when result is already not ok")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    result = verifier.verify_step({"tool": "browser", "target": "youtube"}, {"ok": False})

    assert result is False


# --- app tool verification via _app_is_running -----------------------

def test_verify_step_app_tool_calls_app_is_running(monkeypatch):
    captured = {}

    class FakeCompleted:
        stdout = "true\n"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = verifier.verify_step({"tool": "app", "name": "Safari"}, {"ok": True})

    assert result is True
    assert captured["cmd"][0] == "osascript"
    assert "Safari" in captured["cmd"][2]


def test_verify_step_app_tool_returns_false_when_not_running(monkeypatch):
    class FakeCompleted:
        stdout = "false\n"

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: FakeCompleted())

    result = verifier.verify_step({"tool": "app", "name": "Safari"}, {"ok": True})

    assert result is False


def test_verify_step_app_tool_without_name_trusts_result(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("subprocess.run should not be called without an app name")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    result = verifier.verify_step({"tool": "app", "name": ""}, {"ok": True})

    assert result is True


def test_verify_step_never_raises_on_internal_error(monkeypatch):
    def raise_error(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(subprocess, "run", raise_error)

    result = verifier.verify_step({"tool": "app", "name": "Safari"}, {"ok": True})

    # _app_is_running swallows the exception internally and returns True,
    # so the overall step is trusted as ok.
    assert result is True


# --- _app_is_running behavior directly ---------------------------------

def test_app_is_running_true_when_osascript_reports_true(monkeypatch):
    class FakeCompleted:
        stdout = "true\n"

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: FakeCompleted())

    assert verifier._app_is_running("Safari") is True


def test_app_is_running_defaults_to_true_when_osascript_unavailable(monkeypatch):
    def raise_error(*a, **k):
        raise FileNotFoundError("osascript missing")

    monkeypatch.setattr(subprocess, "run", raise_error)

    # Must not fail the step just because osascript itself couldn't run.
    assert verifier._app_is_running("Safari") is True


# --- AppleScript escaping regression test -------------------------------

def test_app_is_running_escapes_double_quotes_in_app_name(monkeypatch):
    captured = {}

    class FakeCompleted:
        stdout = "true\n"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    verifier._app_is_running('Weird"App')

    script = captured["cmd"][2]
    # The embedded double quote must be escaped as \" rather than left raw,
    # otherwise it would break out of the AppleScript string literal.
    assert 'Weird\\"App' in script
    assert 'Weird"App' not in script
