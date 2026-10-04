import subprocess

import tools.shortcuts as shortcuts


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["shortcuts"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_shortcut_builds_correct_argv_without_input(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed(returncode=0)

    monkeypatch.setattr(shortcuts.subprocess, "run", fake_run)

    result = shortcuts.run_shortcut("My Shortcut")

    assert result is True
    assert captured["cmd"] == ["shortcuts", "run", "My Shortcut"]


def test_run_shortcut_builds_correct_argv_with_input(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed(returncode=0)

    monkeypatch.setattr(shortcuts.subprocess, "run", fake_run)

    result = shortcuts.run_shortcut("My Shortcut", "some input text")

    assert result is True
    assert captured["cmd"] == ["shortcuts", "run", "My Shortcut", "-i", "some input text"]


def test_run_shortcut_handles_empty_shortcut_name():
    assert shortcuts.run_shortcut("") is False
    assert shortcuts.run_shortcut("   ") is False
    assert shortcuts.run_shortcut(None) is False


def test_run_shortcut_returns_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(shortcuts.subprocess, "run", lambda cmd, **kwargs: _completed(returncode=1, stderr="fail"))

    result = shortcuts.run_shortcut("Broken Shortcut")

    assert result is False


def test_run_shortcut_handles_subprocess_timeout(monkeypatch):
    def raise_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 5))

    monkeypatch.setattr(shortcuts.subprocess, "run", raise_timeout)

    result = shortcuts.run_shortcut("Slow Shortcut")

    assert result is False


def test_run_shortcut_handles_generic_exception(monkeypatch):
    def raise_error(cmd, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(shortcuts.subprocess, "run", raise_error)

    result = shortcuts.run_shortcut("Any Shortcut")

    assert result is False


def test_run_shortcut_passes_custom_timeout(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return _completed(returncode=0)

    monkeypatch.setattr(shortcuts.subprocess, "run", fake_run)

    shortcuts.run_shortcut("My Shortcut", timeout=30)

    assert captured["timeout"] == 30
