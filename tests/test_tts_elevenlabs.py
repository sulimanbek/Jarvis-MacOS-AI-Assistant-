import pytest
import requests

import audio.tts as tts


class FakeResponse:
    def __init__(self, status=200, content=b"MP3DATA"):
        self.status_code, self.content, self.text = status, content, "{}"


class FakeCloud:
    """Stands in for requests.post and afplay/say, and records everything."""

    def __init__(self):
        self.posts, self.played, self.said = [], [], []
        self.responder = lambda text: FakeResponse()


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    fake = FakeCloud()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test_key")
    monkeypatch.setattr(tts, "TTS_ENGINE", "auto")
    monkeypatch.setattr(tts, "BRAIN_MODE", "claude")
    monkeypatch.setattr(tts, "VOICE_CACHE_DIR", str(tmp_path / "cache"))

    def post(url, **kw):
        fake.posts.append({"url": url, **kw})
        return fake.responder(kw["json"]["text"])

    class FakePopen:
        def __init__(self, cmd, **kw):
            with open(cmd[1], "rb") as f:  # the file exists while it plays
                fake.played.append((cmd[1], f.read()))

        def wait(self):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(tts.requests, "post", post)
    monkeypatch.setattr(tts.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(tts, "_run_say", lambda text: fake.said.append(text))
    monkeypatch.setattr(tts.subprocess, "run", lambda *a, **k: None)
    return fake


# ── which engine ─────────────────────────────────────────────────────────────

def test_engine_needs_a_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(tts, "TTS_ENGINE", "auto")
    assert tts.tts_engine() == "system"
    assert "ELEVENLABS_API_KEY" in tts.describe_engine()


def test_engine_with_key(cloud):
    assert tts.tts_engine() == "elevenlabs"
    assert "ElevenLabs" in tts.describe_engine()


def test_local_mode_stays_offline_unless_forced(cloud, monkeypatch):
    monkeypatch.setattr(tts, "BRAIN_MODE", "local")
    assert tts.tts_engine() == "system"
    assert "offline" in tts.describe_engine()
    monkeypatch.setattr(tts, "TTS_ENGINE", "elevenlabs")
    assert tts.tts_engine() == "elevenlabs"


def test_system_setting_always_wins(cloud, monkeypatch):
    monkeypatch.setattr(tts, "TTS_ENGINE", "system")
    assert tts.tts_engine() == "system"
    tts._run_speech("hello")
    assert cloud.posts == [] and cloud.said == ["hello"]


# ── the request ──────────────────────────────────────────────────────────────

def test_request_matches_the_elevenlabs_api(cloud):
    tts._run_speech("It is sunny in Dubai.")
    post = cloud.posts[0]
    assert post["url"] == f"https://api.elevenlabs.io/v1/text-to-speech/{tts.ELEVENLABS_VOICE_ID}"
    assert post["headers"]["xi-api-key"] == "sk_test_key"
    assert post["params"] == {"output_format": "mp3_44100_64"}
    body = post["json"]
    assert body["text"] == "It is sunny in Dubai."
    assert body["model_id"] == tts.ELEVENLABS_MODEL
    assert set(body["voice_settings"]) == {"stability", "similarity_boost", "speed"}
    assert post["timeout"] == tts.ELEVENLABS_TIMEOUT


def test_audio_is_played_then_the_temp_file_is_deleted(cloud):
    tts._run_speech("Hello there.")
    path, data = cloud.played[0]
    assert data == b"MP3DATA"
    import os
    assert not os.path.exists(path)
    assert cloud.said == []


def test_reply_is_not_mangled_for_the_cloud_voice(cloud):
    tts._run_speech("Jarvis: The API on macOS is ready")
    assert cloud.posts[0]["json"]["text"] == "The API on macOS is ready."  # label dropped, no "A P I" spelling


def test_long_replies_are_sent_one_sentence_group_at_a_time_in_order(cloud):
    text = " ".join(f"This is sentence number {i} of a rather long reply." for i in range(12))
    tts._run_speech(text)
    sent = [p["json"]["text"] for p in cloud.posts]
    assert len(sent) > 1 and all(len(t) <= 240 for t in sent)
    assert " ".join(sent) == text
    assert len(cloud.played) == len(sent)


# ── fixed phrases are cached ─────────────────────────────────────────────────

def test_fixed_phrases_are_fetched_once_and_then_replayed_from_disk(cloud):
    tts._run_speech("Yes?")
    tts._run_speech("Yes?")
    assert len(cloud.posts) == 1
    assert len(cloud.played) == 2
    assert cloud.played[0][0] == cloud.played[1][0]  # the same cached file


def test_replies_are_never_written_to_the_cache(cloud, tmp_path):
    tts._run_speech("Your bank balance is very private.")
    cache = tmp_path / "cache"
    assert not cache.exists() or list(cache.iterdir()) == []


def test_cache_key_depends_on_the_voice(cloud, monkeypatch):
    a = tts._cache_path("Yes?")
    monkeypatch.setattr(tts, "ELEVENLABS_VOICE_ID", "someone-else")
    assert tts._cache_path("Yes?") != a


# ── falling back to the Mac voice ────────────────────────────────────────────

def test_network_failure_uses_the_mac_voice_and_does_not_retry_for_a_while(cloud):
    def boom(text):
        raise requests.ConnectionError("no network")

    cloud.responder = boom
    tts._run_speech("First.")
    tts._run_speech("Second.")
    assert cloud.said == ["First.", "Second."]
    assert len(cloud.posts) == 1          # the cooldown skipped the second request
    assert cloud.played == []


@pytest.mark.parametrize("status", [401, 403])
def test_bad_key_disables_the_cloud_voice_for_the_session(cloud, status, capsys):
    cloud.responder = lambda text: FakeResponse(status)
    tts._run_speech("One.")
    tts._run_speech("Two.")
    assert cloud.said == ["One.", "Two."]
    assert len(cloud.posts) == 1
    out = capsys.readouterr().out
    assert "rejected the API key" in out and "sk_test_key" not in out


@pytest.mark.parametrize("status", [402, 429, 500, 503])
def test_other_errors_fall_back(cloud, status):
    cloud.responder = lambda text: FakeResponse(status)
    tts._run_speech("Hello.")
    assert cloud.said == ["Hello."]


def test_empty_audio_counts_as_a_failure(cloud):
    cloud.responder = lambda text: FakeResponse(200, b"")
    tts._run_speech("Hello.")
    assert cloud.said == ["Hello."]


def test_missing_player_falls_back(cloud, monkeypatch):
    def nope(*a, **k):
        raise FileNotFoundError("afplay")

    monkeypatch.setattr(tts.subprocess, "Popen", nope)
    tts._run_speech("Hello.")
    assert cloud.said == ["Hello."]


def test_failure_part_way_finishes_the_reply_in_the_mac_voice(cloud):
    text = " ".join(f"This is sentence number {i} of a rather long reply." for i in range(12))
    calls = {"n": 0}

    def flaky(sent):
        calls["n"] += 1
        return FakeResponse() if calls["n"] == 1 else FakeResponse(500)

    cloud.responder = flaky
    tts._run_speech(text)
    assert len(cloud.played) == 1
    assert cloud.said and cloud.said[0].startswith("This is sentence number")
    spoken = " ".join(p["json"]["text"] for p in cloud.posts[:1]) + " " + cloud.said[0]
    assert spoken.replace("  ", " ").count("sentence number") == 12


# ── misc ─────────────────────────────────────────────────────────────────────

def test_blank_text_speaks_nothing(cloud):
    tts._run_speech("   ")
    tts.speak_sync("")
    assert cloud.posts == [] and cloud.played == []


def test_speak_sync_uses_the_active_voice(cloud):
    tts.speak_sync("Yes?")
    assert len(cloud.played) == 1


def test_stopping_speech_terminates_the_player(monkeypatch):
    class P:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    p = P()
    monkeypatch.setattr(tts, "_player", p)
    monkeypatch.setattr(tts.subprocess, "run", lambda *a, **k: None)
    tts._stop_existing_speech()
    assert p.terminated and tts._player is None
