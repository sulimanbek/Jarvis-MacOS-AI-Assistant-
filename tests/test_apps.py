import subprocess

import tools.apps as apps


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["open"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_clean_app_name_strips_filler_words_and_lowercases():
    assert apps.clean_app_name("Open the Safari app") == "safari"


def test_clean_app_name_handles_none_and_empty():
    assert apps.clean_app_name(None) == ""
    assert apps.clean_app_name("") == ""


def test_build_candidates_exact_alias_match():
    candidates = apps._build_candidates("chrome")
    assert candidates[0] == "Google Chrome"


def test_build_candidates_partial_alias_match_included():
    candidates = apps._build_candidates("vs code")
    assert "Visual Studio Code" in candidates


def test_build_candidates_dedupes_preserving_order():
    candidates = apps._build_candidates("safari")
    assert candidates.count("Safari") == 1


def test_build_candidates_empty_for_blank_input():
    assert apps._build_candidates("") == []
    assert apps._build_candidates(None) == []


def test_open_app_succeeds_on_first_candidate(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(returncode=0)

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_app("chrome")

    assert result is True
    assert calls[0] == ["open", "-a", "Google Chrome"]


def test_open_app_falls_through_candidates_on_failure(monkeypatch):
    attempts = []

    def fake_run(cmd, **kwargs):
        attempts.append(cmd[2])
        if cmd[2] == "Google Chrome":
            return _completed(returncode=1, stderr="not found")
        return _completed(returncode=0)

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_app("chrome")

    assert result is True
    assert len(attempts) >= 2


def test_open_app_returns_false_when_no_candidate_works(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _completed(returncode=1, stderr="nope")

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_app("totally unknown thing")

    assert result is False


def test_open_app_returns_false_for_empty_name():
    assert apps.open_app("") is False
    assert apps.open_app(None) is False


def test_open_app_handles_exception_and_continues(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("boom")
        return _completed(returncode=0)

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_app("chrome")

    assert result is True
    assert calls["n"] >= 2


def test_is_app_running_escapes_quotes_in_script(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed(returncode=0, stdout="true")

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.is_app_running('Weird" App')

    assert result is True
    script = captured["cmd"][2]
    assert '\\"' in script
    # The raw unescaped quote must not appear standalone inside the literal
    assert 'Weird" App' not in script


def test_is_app_running_false_when_no_candidate_matches(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _completed(returncode=0, stdout="false")

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    assert apps.is_app_running("safari") is False


def test_is_app_running_false_for_empty_name():
    assert apps.is_app_running("") is False
    assert apps.is_app_running(None) is False


def test_is_app_running_continues_on_exception(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("boom")
        return _completed(returncode=0, stdout="true")

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    assert apps.is_app_running("chrome") is True
