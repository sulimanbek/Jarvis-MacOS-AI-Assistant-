import numpy as np
import pytest

from audio.utterance import DONE, RECORDING, TIMED_OUT, WAITING, UtteranceDetector, rms

CHUNK = 1280


def loud(level=0.1):
    return np.full(CHUNK, level, dtype=np.float32)


def quiet(level=0.002):
    return np.full(CHUNK, level, dtype=np.float32)


def detector(**kw):
    args = dict(onset_energy=0.02, silence_energy=0.008, onset_chunks=3, window_chunks=20,
                silence_chunks=5, max_chunks=50, preroll_chunks=4)
    args.update(kw)
    return UtteranceDetector(**args)


def feed_all(d, chunks):
    states = [d.feed(c) for c in chunks]
    return states


def test_rms_of_empty_and_constant():
    assert rms(np.array([], dtype=np.float32)) == 0.0
    assert rms(np.full(100, 0.5, dtype=np.float32)) == pytest.approx(0.5)


def test_silence_times_out_after_the_window_with_no_audio():
    d = detector()
    states = feed_all(d, [quiet()] * 25)
    assert states[18] == WAITING and states[19] == TIMED_OUT
    assert d.state == TIMED_OUT
    assert d.audio().size == 0


def test_speech_then_silence_records_the_utterance():
    d = detector()
    feed_all(d, [quiet()] * 4 + [loud()] * 10 + [quiet()] * 5)
    assert d.state == DONE
    audio = d.audio()
    assert audio.dtype == np.float32
    # The 10 loud chunks, plus pre-roll from before onset was confirmed.
    assert audio.size >= 10 * CHUNK


def test_preroll_keeps_the_start_of_the_first_word():
    d = detector(onset_chunks=3, preroll_chunks=4)
    # The word starts at chunk 2; onset is only confirmed 3 loud chunks later.
    feed_all(d, [quiet(), quiet(), loud(), loud(), loud(), loud(), quiet(), quiet(), quiet(), quiet(), quiet()])
    audio = d.audio()
    first_loud = np.argmax(audio > 0.05)
    # Onset only fires on the third loud chunk, but the 4-chunk pre-roll still holds the first one,
    # so the start of the word is in the audio. (The very first quiet chunk has aged out.)
    assert first_loud == CHUNK            # the word begins one chunk into the kept audio
    assert audio.size == 10 * CHUNK


def test_a_short_blip_does_not_start_a_recording():
    d = detector(onset_chunks=3)
    feed_all(d, [quiet(), loud(), loud(), quiet(), quiet(), loud(), quiet()])
    assert d.state == WAITING


def test_noise_below_the_onset_level_never_triggers():
    d = detector(window_chunks=30)
    feed_all(d, [np.full(CHUNK, 0.012, dtype=np.float32)] * 40)  # a loud fan, but not speech
    assert d.state == TIMED_OUT


def test_a_pause_shorter_than_the_silence_limit_does_not_end_the_utterance():
    d = detector(silence_chunks=5)
    feed_all(d, [loud()] * 4 + [quiet()] * 3 + [loud()] * 4)
    assert d.state == RECORDING
    feed_all(d, [quiet()] * 5)
    assert d.state == DONE


def test_recording_is_capped():
    d = detector(max_chunks=12)
    feed_all(d, [loud()] * 40)
    assert d.state == DONE
    assert d.audio().size == 12 * CHUNK


def test_state_is_final_once_done_or_timed_out():
    d = detector(window_chunks=3)
    feed_all(d, [quiet()] * 3)
    assert d.state == TIMED_OUT
    assert d.feed(loud()) == TIMED_OUT and d.audio().size == 0


def test_last_rms_is_exposed_for_the_level_meter():
    d = detector()
    d.feed(loud(0.2))
    assert d.last_rms == pytest.approx(0.2, rel=1e-3)


def test_speech_that_starts_right_at_the_end_of_the_window_still_counts():
    d = detector(window_chunks=10, onset_chunks=3)
    feed_all(d, [quiet()] * 7 + [loud()] * 3)
    assert d.state == RECORDING
