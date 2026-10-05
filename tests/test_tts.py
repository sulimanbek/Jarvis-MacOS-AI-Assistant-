import audio.tts as tts


def test_chunk_for_speech_empty_string_returns_empty_list():
    assert tts._chunk_for_speech("") == []
    assert tts._chunk_for_speech("   ") == []


def test_chunk_for_speech_shorter_than_max_len_returns_single_chunk():
    text = "Hello there."
    assert tts._chunk_for_speech(text, max_len=180) == ["Hello there."]


def test_chunk_for_speech_exactly_at_max_len_returns_single_chunk():
    text = "a" * 50
    assert tts._chunk_for_speech(text, max_len=50) == [text]


def test_chunk_for_speech_long_string_no_punctuation_splits_by_length():
    text = "a" * 130
    chunks = tts._chunk_for_speech(text, max_len=50)

    assert chunks == ["a" * 50, "a" * 50, "a" * 30]


def test_chunk_for_speech_long_string_with_sentence_punctuation_splits_on_sentences():
    text = "First sentence here. Second sentence here. Third sentence here."
    chunks = tts._chunk_for_speech(text, max_len=25)

    assert chunks == ["First sentence here.", "Second sentence here.", "Third sentence here."]
    assert all(len(c) <= 25 for c in chunks)


def test_expand_acronyms_expands_short_all_caps_words():
    assert tts._expand_acronyms("call the API now") == "call the A P I now"


def test_expand_acronyms_over_matches_ordinary_all_caps_words():
    # Known edge case: any bare 2-5 letter all-caps word gets "expanded",
    # even when it's not really an acronym (e.g. a shouted word).
    assert tts._expand_acronyms("I AM DONE") == "I A M D O N E"


def test_expand_acronyms_ignores_long_or_lowercase_words():
    assert tts._expand_acronyms("hello world ABCDEFG") == "hello world ABCDEFG"


def test_prepare_tts_text_strips_jarvis_label_and_expands_terms():
    result = tts._prepare_tts_text("Jarvis: I opened PyCharm and macOS settings via GitHub")

    assert not result.startswith("Jarvis:")
    assert "Pie charm" in result
    assert "Mac oh ess" in result
    assert "Git hub" in result


def test_prepare_tts_text_returns_empty_for_blank_input():
    assert tts._prepare_tts_text("") == ""
    assert tts._prepare_tts_text("   ") == ""


def test_prepare_tts_text_adds_terminal_punctuation_when_missing():
    result = tts._prepare_tts_text("no ending punctuation")
    assert result.endswith(".")


def test_prepare_tts_text_keeps_existing_terminal_punctuation():
    result = tts._prepare_tts_text("already a question?")
    assert result.endswith("?")
    assert not result.endswith("?.")


def test_stop_existing_speech_invokes_killall_say(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

    monkeypatch.setattr(tts.subprocess, "run", fake_run)

    tts._stop_existing_speech()

    assert calls == [["killall", "say"]]


def test_stop_existing_speech_swallows_exceptions(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)

    tts._stop_existing_speech()  # must not raise


def test_run_say_invokes_say_with_voice_and_rate(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

    monkeypatch.setattr(tts.subprocess, "run", fake_run)

    tts._run_say("Hello there.")

    # First call is the killall, subsequent calls are "say" invocations
    say_calls = [c for c in calls if c[0] == "say"]
    assert len(say_calls) == 1
    cmd = say_calls[0]
    assert cmd[0] == "say"
    assert "-v" in cmd
    assert tts.TTS_VOICE in cmd
    assert "-r" in cmd
    assert "Hello there." in cmd


def test_run_say_does_nothing_for_blank_text(monkeypatch):
    calls = []
    monkeypatch.setattr(tts.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))

    tts._run_say("   ")

    assert calls == []


def test_speak_does_nothing_for_blank_text(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            started.append((target, args))

        def start(self):
            pass

    monkeypatch.setattr(tts, "Thread", FakeThread)

    tts.speak("")
    tts.speak("   ")

    assert started == []


def test_speak_dispatches_run_say_via_thread(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            started.append((target, args))

        def start(self):
            started[-1][0](*started[-1][1])

    monkeypatch.setattr(tts, "Thread", FakeThread)

    say_calls = []
    monkeypatch.setattr(tts.subprocess, "run", lambda cmd, **kwargs: say_calls.append(cmd))

    tts.speak("hello there")

    assert len(started) == 1
    assert started[0][0] == tts._speak_job
    say_only = [c for c in say_calls if c[0] == "say"]
    assert len(say_only) == 1


def test_speak_ack_picks_from_ack_phrases(monkeypatch):
    captured = {}

    def fake_speak(text):
        captured["text"] = text

    monkeypatch.setattr(tts, "speak", fake_speak)

    tts.speak_ack()

    assert captured["text"] in tts._ACK_PHRASES
