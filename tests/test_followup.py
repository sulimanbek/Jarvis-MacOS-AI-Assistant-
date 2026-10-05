import threading
import time

import numpy as np
import pytest

import audio.listener as listener_mod
import audio.tts as tts
import daemon
from audio.listener import ContinuousListener
from core.state_machine import JarvisState


class Audio:
    """Stands in for a numpy array: only .size matters to the daemon."""

    def __init__(self, size=100):
        self.size = size


class Conversation:
    """A listener whose follow-up windows are scripted: Audio, or EMPTY for silence."""

    EMPTY = Audio(0)

    def __init__(self, replies):
        self.replies = list(replies)
        self.windows = []

    def listen_for_followup(self, window):
        self.windows.append(window)
        item = self.replies.pop(0) if self.replies else self.EMPTY
        return item, 16000


@pytest.fixture
def convo(monkeypatch):
    """The daemon with everything outside the follow-up loop replaced."""
    calls = {"transcripts": [], "commands": [], "waits": 0}
    monkeypatch.setattr(daemon, "FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(daemon, "FOLLOWUP_MAX_TURNS", 25)
    monkeypatch.setattr(daemon, "emit_event", lambda *a, **k: None)
    monkeypatch.setattr(daemon, "save_action", lambda *a, **k: None)

    def waiter(*a, **k):
        calls["waits"] += 1
        return True

    monkeypatch.setattr(daemon, "wait_until_quiet", waiter)

    def set_texts(texts):
        queue = list(texts)

        def transcribe(audio, sr):
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        monkeypatch.setattr(daemon, "transcribe", transcribe)

    def set_outcomes(outcome_for=None):
        def process(text, listener):
            calls["commands"].append(text)
            return (outcome_for or (lambda t: None))(text)

        monkeypatch.setattr(daemon, "_process_command", process)

    set_outcomes()
    calls["set_texts"], calls["set_outcomes"] = set_texts, set_outcomes
    return calls


# ── the conversation loop ────────────────────────────────────────────────────

def test_keeps_listening_across_several_replies_then_ends_on_silence(convo):
    convo["set_texts"](["what's the weather", "and tomorrow", "will I need a coat"])
    listener = Conversation([Audio(), Audio(), Audio()])
    result = daemon._follow_up(listener, JarvisState())
    assert result is None
    assert convo["commands"] == ["what's the weather", "and tomorrow", "will I need a coat"]
    assert len(listener.windows) == 4                     # three replies, then the silent window
    assert all(w == daemon.FOLLOWUP_SECONDS for w in listener.windows)


def test_waits_for_jarvis_to_stop_talking_before_every_listen(convo):
    convo["set_texts"](["one", "two"])
    daemon._follow_up(Conversation([Audio(), Audio()]), JarvisState())
    assert convo["waits"] == 3


def test_silence_ends_it_immediately(convo):
    listener = Conversation([])
    assert daemon._follow_up(listener, JarvisState()) is None
    assert convo["commands"] == [] and len(listener.windows) == 1


@pytest.mark.parametrize("phrase", [
    "Thanks.", "thank you", "Thanks, Jarvis!", "That's all.", "that’s all", "Never mind", "nevermind",
    "no thanks", "OK, thanks.", "stop", "cancel",
])
def test_closing_phrases_end_the_conversation_without_running_a_command(convo, phrase):
    convo["set_texts"]([phrase])
    listener = Conversation([Audio(), Audio()])
    assert daemon._follow_up(listener, JarvisState()) is None
    assert convo["commands"] == []
    assert len(listener.windows) == 1                     # it did not keep listening


@pytest.mark.parametrize("junk", [
    "", "   ", "[BLANK_AUDIO]", "(music)", "*coughs*", "you", "Thank you for watching!", "uh", ".", "a", "Hmm.",
])
def test_whispers_inventions_from_noise_are_ignored(convo, junk):
    convo["set_texts"]([junk])
    assert daemon._follow_up(Conversation([Audio()]), JarvisState()) is None
    assert convo["commands"] == []


def test_a_real_sentence_that_contains_a_closing_word_is_still_a_command(convo):
    convo["set_texts"](["thanks, now open safari", "nothing"])
    daemon._follow_up(Conversation([Audio(), Audio()]), JarvisState())
    assert convo["commands"] == ["thanks, now open safari"]


def test_a_transcription_error_ends_it_quietly(convo):
    convo["set_texts"]([RuntimeError("whisper died")])
    assert daemon._follow_up(Conversation([Audio()]), JarvisState()) is None
    assert convo["commands"] == []


def test_goodbye_in_a_conversation_still_shuts_jarvis_down(convo):
    convo["set_texts"](["goodbye"])
    convo["set_outcomes"](lambda t: "exit" if t == "goodbye" else None)
    assert daemon._follow_up(Conversation([Audio()]), JarvisState()) == "exit"


def test_the_back_to_back_cap_stops_a_runaway_conversation(convo, monkeypatch):
    monkeypatch.setattr(daemon, "FOLLOWUP_MAX_TURNS", 3)
    convo["set_texts"](["a b", "c d", "e f", "g h", "i j"])
    daemon._follow_up(Conversation([Audio()] * 5), JarvisState())
    assert len(convo["commands"]) == 3


def test_state_goes_listening_then_back_to_speaking(convo):
    convo["set_texts"](["what time is it"])
    state, seen = JarvisState(), []
    orig = state.transition
    state.transition = lambda s: (seen.append(s.name), orig(s))[1]
    daemon._follow_up(Conversation([Audio()]), state)
    assert seen[0] == "LISTENING" and "EXECUTING" in seen and seen[-1] == "LISTENING"


# ── noise detection ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("open safari", False), ("what's the weather like", False), ("no", False), ("yes", False),
    ("ok", False), ("[BLANK_AUDIO]", True), ("(silence)", True), ("you", True), ("", True),
])
def test_is_noise(text, expected):
    assert daemon._is_noise(text) is expected


# ── confirmations no longer need the wake word ──────────────────────────────

def test_confirmation_listens_without_the_wake_word_and_after_the_question_is_spoken(monkeypatch):
    order = []
    monkeypatch.setattr(daemon, "speak", lambda t: order.append(("speak", t)))
    monkeypatch.setattr(daemon, "wait_until_quiet", lambda **k: order.append(("wait", k)) or True)
    monkeypatch.setattr(daemon, "transcribe", lambda a, sr: "yes please")

    class L:
        def listen_for_followup(self, window):
            order.append(("listen", window))
            return Audio(), 16000

        def listen_for_command(self):
            raise AssertionError("must not wait for the wake word")

    assert daemon._confirm_action(L(), {"tool": "shortcut"}) is True
    kinds = [o[0] for o in order]
    assert kinds == ["speak", "wait", "listen"]
    assert "wake word" not in order[0][1]


# ── waiting for Jarvis to finish speaking ───────────────────────────────────

def test_wait_until_quiet_returns_at_once_when_nothing_is_playing():
    t0 = time.monotonic()
    assert tts.wait_until_quiet(timeout=5, settle=2) is True
    assert time.monotonic() - t0 < 0.5      # no settle pause when nothing was said


def test_wait_until_quiet_blocks_until_speech_is_done_then_settles(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(tts, "_run_speech", lambda text: release.wait(5))
    tts.speak("a long reply")
    done = {}

    def waiter():
        t0 = time.monotonic()
        done["ok"] = tts.wait_until_quiet(timeout=5, settle=0.2)
        done["took"] = time.monotonic() - t0

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.15)
    assert t.is_alive()                      # still waiting: Jarvis is still talking
    release.set()
    t.join(3)
    assert done["ok"] is True and done["took"] >= 0.2   # waited for the end, then settled


def test_wait_until_quiet_times_out_instead_of_hanging(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(tts, "_run_speech", lambda text: release.wait(5))
    tts.speak("stuck")
    assert tts.wait_until_quiet(timeout=0.2) is False
    release.set()
    assert tts.wait_until_quiet(timeout=2) is True


def test_a_failing_speech_job_still_releases_the_waiter(monkeypatch, capsys):
    def boom(text):
        raise RuntimeError("tts exploded")

    monkeypatch.setattr(tts, "_run_speech", boom)
    tts.speak("x")
    assert tts.wait_until_quiet(timeout=2) is True
    assert "tts exploded" in capsys.readouterr().out


# ── the listener, with a fake microphone ─────────────────────────────────────

class FakeStream:
    """Feeds scripted chunks to the callback on a thread, like sounddevice does."""

    script: list = []

    def __init__(self, samplerate, channels, dtype, blocksize, callback):
        self.callback, self.stop = callback, threading.Event()

    def __enter__(self):
        def run():
            for chunk in list(FakeStream.script):
                if self.stop.is_set():
                    return
                try:
                    self.callback(chunk.reshape(-1, 1), len(chunk), None, None)
                except listener_mod.sd.CallbackStop:
                    return
                time.sleep(0.001)

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.thread.join(2)


class DummyDetector:
    def __init__(self, *a, **k):
        pass


@pytest.fixture
def mic(monkeypatch):
    monkeypatch.setattr(listener_mod, "WakeWordDetector", DummyDetector)
    monkeypatch.setattr(listener_mod.sd, "InputStream", FakeStream)
    levels = []
    lst = ContinuousListener(on_level=levels.append)
    lst.levels = levels
    return lst


def chunk(level):
    return np.full(listener_mod.CHUNK_SAMPLES, level, dtype=np.float32)


def test_listener_returns_the_spoken_reply(mic):
    FakeStream.script = [chunk(0.002)] * 3 + [chunk(0.1)] * 8 + [chunk(0.002)] * 40
    audio, sr = mic.listen_for_followup(5)
    assert sr == listener_mod.AUDIO_SAMPLE_RATE
    assert audio.size >= 8 * listener_mod.CHUNK_SAMPLES
    assert audio.dtype == np.float32 and float(np.abs(audio).max()) == pytest.approx(0.1)


def test_listener_returns_nothing_when_no_one_speaks(mic):
    FakeStream.script = [chunk(0.003)] * 200
    audio, _ = mic.listen_for_followup(1)       # ~12 chunks of window
    assert audio.size == 0


def test_listener_reports_levels_for_the_hud_and_ends_at_zero(mic):
    FakeStream.script = [chunk(0.1)] * 8 + [chunk(0.002)] * 40
    mic.listen_for_followup(5)
    assert any(v > 0.05 for v in mic.levels) and mic.levels[-1] == 0.0


def test_listener_stops_promptly_when_asked(mic):
    mic.stop()
    FakeStream.script = [chunk(0.1)] * 50
    t0 = time.monotonic()
    audio, _ = mic.listen_for_followup(5)
    assert audio.size == 0
    assert time.monotonic() - t0 < 2      # not the 20+ seconds of the full window
