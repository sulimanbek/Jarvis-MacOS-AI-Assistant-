"""
core/level_stream.py

Streams the microphone level to the HUD so the ring reacts to your voice.

The audio callbacks call push() with a raw RMS value. That is a single attribute
write, so nothing in the real-time audio thread can block. A separate thread
sends the latest value about 15 times a second, and only when it has changed.

Only a single number between 0 and 1 leaves this process, never audio.
"""

import contextlib
import threading
from collections.abc import Callable

from core.bridge_client import get_client

# Room noise sits around 0.002-0.008 RMS; speech at arm's length is 0.03-0.15.
GATE = 0.008     # below this is treated as silence
GAIN = 14.0
CURVE = 0.7      # < 1 lifts quiet speech so it still visibly moves the ring

SEND_INTERVAL = 1 / 15
MIN_CHANGE = 0.02


def shape(rms: float) -> float:
    """Turn a raw RMS value into a 0..1 level for the HUD."""
    x = max(0.0, float(rms) - GATE)
    return min(1.0, (x * GAIN) ** CURVE)


class LevelStreamer:
    def __init__(self, send: Callable[[float], None] | None = None,
                 interval: float = SEND_INTERVAL):
        self._send = send or (lambda v: get_client().emit_level(v))
        self._interval = interval
        self._latest = 0.0
        self._last_sent = -1.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def push(self, rms: float) -> None:
        """Called from the audio thread. Just records the newest value."""
        self._latest = shape(rms)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="level-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            v = self._latest
            changed = abs(v - self._last_sent) >= MIN_CHANGE
            # Always send the return to silence, or the ring could stick open.
            settled = v == 0.0 and self._last_sent != 0.0
            if changed or settled:
                self._last_sent = v
                with contextlib.suppress(Exception):
                    self._send(v)
