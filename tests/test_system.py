import os
import subprocess

import tools.system as system


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_osascript_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0))
    assert system._run_osascript("do something") is True


def test_run_osascript_returns_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1, stderr="nope"))
    assert system._run_osascript("do something") is False


def test_run_osascript_returns_false_on_exception(monkeypatch):
    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="osascript", timeout=5)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    assert system._run_osascript("do something") is False


def test_run_shell_returns_ok_and_stdout_on_success(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0, stdout="  hi  "))
    ok, output = system._run_shell(["echo", "hi"])
    assert ok is True
    assert output == "hi"


def test_run_shell_falls_back_to_stderr_when_stdout_empty(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1, stdout="", stderr="bad"))
    ok, output = system._run_shell(["false"])
    assert ok is False
    assert output == "bad"


def test_run_shell_returns_false_and_error_message_on_exception(monkeypatch):
    def raise_error(*a, **k):
        raise OSError("no such command")

    monkeypatch.setattr(subprocess, "run", raise_error)
    ok, output = system._run_shell(["nonexistent"])
    assert ok is False
    assert "no such command" in output


def test_get_current_volume_parses_and_clamps_output(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0, stdout="150\n"))
    assert system._get_current_volume() == 100


def test_get_current_volume_returns_zero_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1))
    assert system._get_current_volume() == 0


def test_get_current_volume_returns_zero_on_exception(monkeypatch):
    def raise_error(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(subprocess, "run", raise_error)
    assert system._get_current_volume() == 0


def test_get_output_volume_delegates_to_get_current_volume(monkeypatch):
    monkeypatch.setattr(system, "_get_current_volume", lambda: 42)
    assert system.get_output_volume() == 42


def test_is_output_muted_true_when_osascript_says_true(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0, stdout="true\n"))
    assert system.is_output_muted() is True


def test_is_output_muted_false_when_osascript_says_false(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0, stdout="false\n"))
    assert system.is_output_muted() is False


def test_is_output_muted_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1))
    assert system.is_output_muted() is False


def test_is_output_muted_false_on_exception(monkeypatch):
    def raise_error(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(subprocess, "run", raise_error)
    assert system.is_output_muted() is False


def test_brightness_up_calls_run_shell_with_expected_cmd(monkeypatch):
    captured = {}

    def fake_run_shell(cmd):
        captured["cmd"] = cmd
        return True, ""

    monkeypatch.setattr(system, "_run_shell", fake_run_shell)
    assert system.brightness_up() is True
    assert captured["cmd"] == ["brightness", "0.1+"]


def test_brightness_down_calls_run_shell_with_expected_cmd(monkeypatch):
    captured = {}

    def fake_run_shell(cmd):
        captured["cmd"] = cmd
        return True, ""

    monkeypatch.setattr(system, "_run_shell", fake_run_shell)
    assert system.brightness_down() is True
    assert captured["cmd"] == ["brightness", "0.1-"]


def test_lock_screen_calls_run_shell_and_reports_failure(monkeypatch):
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (False, "denied"))
    assert system.lock_screen() is False


def test_sleep_display_calls_run_shell_with_expected_cmd(monkeypatch):
    captured = {}

    def fake_run_shell(cmd):
        captured["cmd"] = cmd
        return True, ""

    monkeypatch.setattr(system, "_run_shell", fake_run_shell)
    assert system.sleep_display() is True
    assert captured["cmd"] == ["pmset", "displaysleepnow"]


def test_set_volume_calls_run_osascript_with_clamped_value(monkeypatch):
    captured = {}

    def fake_run_osascript(script):
        captured["script"] = script
        return True

    monkeypatch.setattr(system, "_run_osascript", fake_run_osascript)

    result = system.set_volume(150)

    assert result is True
    assert "100" in captured["script"]


def test_set_volume_clamps_negative_to_zero(monkeypatch):
    captured = {}
    monkeypatch.setattr(system, "_run_osascript", lambda script: captured.setdefault("script", script) or True)

    system.set_volume(-20)

    assert "set volume output volume 0" in captured["script"]


def test_change_volume_adds_delta_to_current(monkeypatch):
    monkeypatch.setattr(system, "_get_current_volume", lambda: 40)
    captured = {}

    def fake_run_osascript(script):
        captured["script"] = script
        return True

    monkeypatch.setattr(system, "_run_osascript", fake_run_osascript)

    result = system.change_volume(10)

    assert result is True
    assert "set volume output volume 50" in captured["script"]


def test_change_volume_clamps_when_exceeding_max(monkeypatch):
    monkeypatch.setattr(system, "_get_current_volume", lambda: 95)
    captured = {}

    def fake_run_osascript(script):
        captured["script"] = script
        return True

    monkeypatch.setattr(system, "_run_osascript", fake_run_osascript)

    system.change_volume(20)

    assert "set volume output volume 100" in captured["script"]


def test_get_battery_status_parses_discharging_string(monkeypatch):
    sample = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=123)\t87%; discharging; 3:47 remaining present: true"
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (True, sample))

    result = system.get_battery_status()

    assert result == "Your battery is at 87 percent and is not charging."


def test_get_battery_status_parses_charging_string(monkeypatch):
    sample = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=123)\t54%; charging; 1:12 remaining present: true"
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (True, sample))

    result = system.get_battery_status()

    assert result == "Your battery is at 54 percent and is charging."


def test_get_battery_status_handles_malformed_output(monkeypatch):
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (True, "no useful info here"))

    result = system.get_battery_status()

    assert result == "I couldn't read the battery percentage."


def test_get_battery_status_returns_none_when_shell_fails(monkeypatch):
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (False, ""))

    assert system.get_battery_status() is None


def test_get_battery_status_returns_none_for_empty_output(monkeypatch):
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (True, ""))

    assert system.get_battery_status() is None


def test_take_screenshot_generates_desktop_path_and_returns_it(monkeypatch, tmp_path):
    def fake_run_shell(cmd):
        # Simulate screencapture creating the file at the requested path
        target_path = cmd[-1]
        with open(target_path, "w") as f:
            f.write("fake png")
        return True, ""

    monkeypatch.setattr(system, "_run_shell", fake_run_shell)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / p.split("/")[-1]))

    result = system.take_screenshot()

    assert result is not None
    assert result.endswith(".png")
    assert "Jarvis Screenshot" in result


def test_take_screenshot_returns_none_when_capture_fails(monkeypatch):
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (False, "error"))

    result = system.take_screenshot()

    assert result is None


def test_read_clipboard_returns_output_on_success(monkeypatch):
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (True, "clipboard contents"))

    assert system.read_clipboard() == "clipboard contents"


def test_read_clipboard_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(system, "_run_shell", lambda cmd: (False, ""))

    assert system.read_clipboard() is None


def test_mute_and_unmute_call_run_osascript(monkeypatch):
    captured = []
    monkeypatch.setattr(system, "_run_osascript", lambda script: captured.append(script) or True)

    assert system.mute() is True
    assert system.unmute() is True
    assert "muted" in captured[0]
    assert "without output muted" in captured[1]
