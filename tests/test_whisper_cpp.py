import subprocess

import numpy as np
import pytest

import core.stt.whisper_cpp as whisper_cpp


def _valid_audio():
    return np.zeros(1600, dtype=np.float32)


def test_transcribe_raises_file_not_found_when_binary_missing(monkeypatch):
    monkeypatch.setattr(whisper_cpp.os.path, "isfile", lambda path: False)

    with pytest.raises(FileNotFoundError, match="Whisper binary not found"):
        whisper_cpp.transcribe(_valid_audio())


def test_transcribe_raises_file_not_found_when_model_missing(monkeypatch):
    # Binary exists, model does not
    monkeypatch.setattr(
        whisper_cpp.os.path, "isfile",
        lambda path: path == whisper_cpp.os.path.expanduser(whisper_cpp.WHISPER_BIN),
    )

    with pytest.raises(FileNotFoundError, match="Whisper model not found"):
        whisper_cpp.transcribe(_valid_audio())


def test_transcribe_empty_audio_returns_empty_string(monkeypatch):
    monkeypatch.setattr(whisper_cpp.os.path, "isfile", lambda path: True)

    def fail_if_called(*a, **k):
        raise AssertionError("subprocess.run should not be called for empty audio")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    result = whisper_cpp.transcribe(np.zeros(0, dtype=np.float32))

    assert result == ""


def test_transcribe_none_audio_returns_empty_string(monkeypatch):
    monkeypatch.setattr(whisper_cpp.os.path, "isfile", lambda path: True)
    result = whisper_cpp.transcribe(None)
    assert result == ""


def test_transcribe_success_reads_output_file(monkeypatch):
    monkeypatch.setattr(whisper_cpp.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(whisper_cpp.sf, "write", lambda path, data, rate: None)

    def fake_run(cmd, **kwargs):
        # Write the expected output file so the real Path.exists() sees it,
        # mirroring what whisper-cli would produce.
        of_index = cmd.index("-of")
        out_base = cmd[of_index + 1]
        with open(out_base + ".txt", "w", encoding="utf-8") as f:
            f.write("hello world\n")

        class FakeCompleted:
            pass

        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = whisper_cpp.transcribe(_valid_audio())

    assert result == "hello world"


def test_transcribe_called_process_error_converts_to_runtime_error(monkeypatch):
    monkeypatch.setattr(whisper_cpp.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(whisper_cpp.sf, "write", lambda path, data, rate: None)

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="whisper exploded")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="whisper.cpp transcription failed") as exc_info:
        whisper_cpp.transcribe(_valid_audio())
    assert "whisper exploded" in str(exc_info.value)


def test_transcribe_timeout_expired_converts_to_runtime_error(monkeypatch):
    monkeypatch.setattr(whisper_cpp.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(whisper_cpp.sf, "write", lambda path, data, rate: None)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout=60)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="whisper.cpp transcription timed out"):
        whisper_cpp.transcribe(_valid_audio())


def test_transcribe_missing_output_file_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(whisper_cpp.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(whisper_cpp.sf, "write", lambda path, data, rate: None)

    class FakeCompleted:
        pass

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: FakeCompleted())

    with pytest.raises(RuntimeError, match="did not produce a transcription file"):
        whisper_cpp.transcribe(_valid_audio())
