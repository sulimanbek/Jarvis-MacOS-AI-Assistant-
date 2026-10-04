import time

import numpy as np

import audio.clap_trigger as clap_trigger


def _silence(n=512):
    return np.zeros((n, 1), dtype="float32")


def _loud(n=512, amplitude=1.0):
    return np.full((n, 1), amplitude, dtype="float32")


def _make_trigger(monkeypatch):
    triggered = {"count": 0}

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None, name=None):
            self._target = target
            self._args = args

        def start(self):
            # Run synchronously so tests can observe the effect immediately.
            self._target(*self._args)

    monkeypatch.setattr(clap_trigger.threading, "Thread", FakeThread)

    def on_trigger():
        triggered["count"] += 1

    trigger = clap_trigger.ClapTrigger(on_trigger=on_trigger)
    return trigger, triggered


def test_callback_ignores_silence(monkeypatch):
    trigger, triggered = _make_trigger(monkeypatch)

    trigger._callback(_silence(), 512, None, None)
    trigger._callback(_silence(), 512, None, None)

    assert triggered["count"] == 0
    assert trigger._in_clap is False
    assert trigger._first_clap_time is None


def test_callback_single_clap_alone_does_not_trigger(monkeypatch):
    trigger, triggered = _make_trigger(monkeypatch)

    trigger._callback(_loud(), 512, None, None)
    trigger._callback(_silence(), 512, None, None)

    assert triggered["count"] == 0
    assert trigger._first_clap_time is not None


def test_callback_two_claps_within_max_gap_triggers(monkeypatch):
    trigger, triggered = _make_trigger(monkeypatch)

    # First clap: rising edge then falling edge.
    trigger._callback(_loud(), 512, None, None)
    trigger._callback(_silence(), 512, None, None)

    # Force the recorded first-clap time so the gap falls comfortably
    # inside [CLAP_MIN_GAP_MS, CLAP_MAX_GAP_MS] regardless of test speed.
    gap_seconds = (clap_trigger.CLAP_MIN_GAP_MS + clap_trigger.CLAP_MAX_GAP_MS) / 2 / 1000
    trigger._first_clap_time = time.monotonic() - gap_seconds

    # Second clap: rising edge triggers detection.
    trigger._callback(_loud(), 512, None, None)

    assert triggered["count"] == 1
    # State should be reset after a successful trigger.
    assert trigger._first_clap_time is None
    assert trigger._in_clap is False


def test_callback_gap_longer_than_max_resets_to_fresh_first_clap(monkeypatch):
    trigger, triggered = _make_trigger(monkeypatch)

    trigger._callback(_loud(), 512, None, None)
    trigger._callback(_silence(), 512, None, None)

    # Simulate a first clap that happened long ago (gap too large).
    too_long_ago = (clap_trigger.CLAP_MAX_GAP_MS + 400) / 1000
    trigger._first_clap_time = time.monotonic() - too_long_ago

    before = trigger._first_clap_time
    trigger._callback(_loud(), 512, None, None)

    assert triggered["count"] == 0
    # The impulse should be treated as a fresh first clap, not the old one.
    assert trigger._first_clap_time is not None
    assert trigger._first_clap_time != before


def test_callback_gap_too_short_is_ignored_and_stays_in_clap(monkeypatch):
    trigger, triggered = _make_trigger(monkeypatch)

    trigger._callback(_loud(), 512, None, None)
    trigger._callback(_silence(), 512, None, None)

    # Gap smaller than CLAP_MIN_GAP_MS.
    too_soon = (clap_trigger.CLAP_MIN_GAP_MS / 2) / 1000
    original_first_clap_time = time.monotonic() - too_soon
    trigger._first_clap_time = original_first_clap_time

    trigger._callback(_loud(), 512, None, None)

    assert triggered["count"] == 0
    # First clap time is left untouched since gap_ms < CLAP_MIN_GAP_MS.
    assert trigger._first_clap_time == original_first_clap_time
    assert trigger._in_clap is True


def test_callback_sustained_loud_sound_resets_after_max_duration(monkeypatch):
    trigger, triggered = _make_trigger(monkeypatch)

    trigger._callback(_loud(), 512, None, None)
    assert trigger._in_clap is True

    # Keep feeding loud blocks, one at a time, stopping the instant the
    # sustained-duration reset fires (further loud blocks would just start
    # a brand-new impulse and mask the assertion).
    reset_happened = False
    for _ in range(50):
        trigger._callback(_loud(), 512, None, None)
        if trigger._in_clap is False:
            reset_happened = True
            break

    assert reset_happened
    assert trigger._first_clap_time is None
    assert triggered["count"] == 0


def test_callback_stop_event_set_raises_callback_stop(monkeypatch):
    trigger, _ = _make_trigger(monkeypatch)
    trigger._stop_event.set()

    raised = False
    try:
        trigger._callback(_silence(), 512, None, None)
    except clap_trigger.sd.CallbackStop:
        raised = True

    assert raised
