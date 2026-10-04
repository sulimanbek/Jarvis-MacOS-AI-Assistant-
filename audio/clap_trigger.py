"""
audio/clap_trigger.py

Detects a double-clap pattern using audio energy analysis.
Runs continuously in a background thread at minimal CPU cost —
it only measures RMS energy per block, no full ML inference.

Pattern:   [CLAP] ──gap 150–700ms── [CLAP]  →  trigger fires
"""

import threading
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from config import (
    AUDIO_SAMPLE_RATE,
    CLAP_ENERGY_THRESHOLD,
    CLAP_MAX_DURATION_MS,
    CLAP_MAX_GAP_MS,
    CLAP_MIN_GAP_MS,
)

# 32ms blocks at 16kHz — light enough for continuous monitoring
_BLOCK_SIZE = 512


class ClapTrigger:
    """
    Listens for a double-clap and calls on_trigger() when detected.

    Usage:
        trigger = ClapTrigger(on_trigger=my_callback)
        trigger.start()
        ...
        trigger.stop()
    """

    def __init__(self, on_trigger: Callable[[], None]):
        self.on_trigger = on_trigger
        self._stop_event  = threading.Event()
        self._thread: threading.Thread | None = None

        # Detection state (mutated only inside audio callback)
        self._in_clap         = False
        self._clap_duration_ms = 0.0
        self._first_clap_time: float | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ClapTrigger")
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    # ── Internal ─────────────────────────────────────────────────────────

    def _run(self):
        try:
            with sd.InputStream(
                samplerate=AUDIO_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=_BLOCK_SIZE,
                callback=self._callback,
            ):
                self._stop_event.wait()
        except Exception as e:
            print(f"[ClapTrigger] Stream error: {e}")

    def _callback(self, indata, frames, time_info, status):
        if self._stop_event.is_set():
            raise sd.CallbackStop()

        rms = float(np.sqrt(np.mean(indata ** 2)))
        now = time.monotonic()
        block_ms = (_BLOCK_SIZE / AUDIO_SAMPLE_RATE) * 1000
        is_loud = rms >= CLAP_ENERGY_THRESHOLD

        if is_loud and not self._in_clap:
            # ── Rising edge: new impulse detected ────────────────────────
            self._in_clap = True
            self._clap_duration_ms = block_ms

            if self._first_clap_time is None:
                # First clap — just record the time
                self._first_clap_time = now
            else:
                gap_ms = (now - self._first_clap_time) * 1000
                if CLAP_MIN_GAP_MS <= gap_ms <= CLAP_MAX_GAP_MS:
                    # Valid double clap — fire trigger in its own thread
                    self._reset()
                    threading.Thread(target=self.on_trigger, daemon=True).start()
                elif gap_ms > CLAP_MAX_GAP_MS:
                    # Gap too long — treat this impulse as a fresh first clap
                    self._first_clap_time = now
                # gap_ms < CLAP_MIN_GAP_MS → too fast, ignore (still in_clap=True)

        elif is_loud and self._in_clap:
            # ── Sustained loud sound: accumulate duration ─────────────────
            self._clap_duration_ms += block_ms
            if self._clap_duration_ms > CLAP_MAX_DURATION_MS:
                # Too long to be a clap (speech, music, etc.) — reset
                self._reset()

        elif not is_loud and self._in_clap:
            # ── Falling edge: impulse ended ───────────────────────────────
            self._in_clap = False
            self._clap_duration_ms = 0.0

        # Global timeout: if first clap was too long ago, forget it
        if self._first_clap_time and (now - self._first_clap_time) * 1000 > CLAP_MAX_GAP_MS + 300:
            self._first_clap_time = None

    def _reset(self):
        self._in_clap          = False
        self._clap_duration_ms = 0.0
        self._first_clap_time  = None
