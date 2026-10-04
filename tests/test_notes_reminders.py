import subprocess

import tools.notes as notes
import tools.reminders as reminders


def _completed(returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=["osascript"], returncode=returncode, stdout="", stderr=stderr)


def test_add_note_escapes_quotes_and_backslashes(monkeypatch):
    captured = {}

    def fake_run_applescript(script):
        captured["script"] = script
        return _completed(returncode=0)

    monkeypatch.setattr(notes, "run_applescript", fake_run_applescript)

    result = notes.add_note('Say "hi" \\ there')

    assert result is True
    assert '\\"hi\\"' in captured["script"]
    assert "\\\\" in captured["script"]


def test_add_note_returns_false_for_empty_text():
    assert notes.add_note("") is False
    assert notes.add_note(None) is False


def test_add_note_returns_false_on_applescript_failure(monkeypatch):
    monkeypatch.setattr(notes, "run_applescript", lambda script: _completed(returncode=1, stderr="nope"))

    result = notes.add_note("buy milk")

    assert result is False


def test_add_reminder_escapes_quotes_and_backslashes(monkeypatch):
    captured = {}

    def fake_run_applescript(script):
        captured["script"] = script
        return _completed(returncode=0)

    monkeypatch.setattr(reminders, "run_applescript", fake_run_applescript)

    result = reminders.add_reminder('Call "Bob" \\ now')

    assert result is True
    assert '\\"Bob\\"' in captured["script"]
    assert "\\\\" in captured["script"]


def test_add_reminder_returns_false_for_empty_text():
    assert reminders.add_reminder("") is False
    assert reminders.add_reminder(None) is False


def test_add_reminder_returns_false_on_applescript_failure(monkeypatch):
    monkeypatch.setattr(reminders, "run_applescript", lambda script: _completed(returncode=1, stderr="nope"))

    result = reminders.add_reminder("walk the dog")

    assert result is False
