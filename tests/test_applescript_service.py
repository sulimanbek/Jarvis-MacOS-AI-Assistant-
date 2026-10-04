import subprocess

import pytest

import services.applescript as applescript


def test_run_applescript_returns_completed_process_on_success(monkeypatch):
    expected = subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="ok", stderr="")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    result = applescript.run_applescript('tell application "Finder" to activate')

    assert result is expected
    assert captured["cmd"] == ["osascript", "-e", 'tell application "Finder" to activate']
    assert captured["kwargs"]["timeout"] > 0


def test_run_applescript_reraises_timeout_expired(monkeypatch):
    def raise_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

    monkeypatch.setattr(applescript.subprocess, "run", raise_timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        applescript.run_applescript("some script")


def test_run_applescript_reraises_other_exceptions(monkeypatch):
    def raise_error(cmd, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(applescript.subprocess, "run", raise_error)

    with pytest.raises(OSError, match="boom"):
        applescript.run_applescript("some script")


def test_escape_applescript_text_escapes_backslashes_and_quotes():
    result = applescript.escape_applescript_text('say "hi" \\ there')

    assert result == 'say \\"hi\\" \\\\ there'


def test_escape_applescript_text_handles_none_and_empty():
    assert applescript.escape_applescript_text(None) == ""
    assert applescript.escape_applescript_text("") == ""


def test_escape_applescript_text_backslash_before_quote_order():
    # Ensure backslashes are escaped first so quote-escaping doesn't double-escape
    result = applescript.escape_applescript_text('a\\"b')
    assert result == 'a\\\\\\"b'
