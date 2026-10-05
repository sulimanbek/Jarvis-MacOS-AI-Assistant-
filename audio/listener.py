import contextlib
import threading
import time
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from audio.tts import speak_sync
from audio.wake_word import CHUNK_SAMPLES, WakeWordDetector
from config import (
    AUDIO_CHANNELS,
    AUDIO_DTYPE,
    AUDIO_SAMPLE_RATE,
    CLAP_ENERGY_THRESHOLD,
    CLAP_MAX_DURATION_MS,
    CLAP_MAX_GAP_MS,
    CLAP_MIN_GAP_MS,
    WAKE_WORD_MODEL,
    WAKE_WORD_THRESHOLD,
)

# How long silence must last before we consider the command finished
VAD_SILENCE_SECONDS = 1.5
# RMS energy below this is considered silence
VAD_ENERGY_THRESHOLD = 0.008
# Hard cap on command length
MAX_COMMAND_SECONDS = 12

_BLOCK_MS = (CHUNK_SAMPLES / AUDIO_SAMPLE_RATE) * 1000


@dataclass
class _ClapState:
    in_clap: bool = False
    duration_ms: float = 0.0
    first_time: float | None = None


def _speak_sync(text: str):
    """Blocking TTS — used between audio streams so mic doesn't pick up Jarvis's voice."""
    speak_sync(text)


class ContinuousListener:
    def __init__(self, on_triggered=None, on_level=None):
        self.detector = WakeWordDetector(WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD)
        self._stop_event = threading.Event()
        # Called once when a wake word or double clap fires, before "Yes?".
        self.on_triggered = on_triggered
        # Called with each chunk's RMS, from the audio thread: keep it trivial.
        self.on_level = on_level

    def stop(self):
        self._stop_event.set()

    def listen_for_command(self) -> tuple[np.ndarray, int]:
        """
        Block until wake word heard or double-clap detected (single stream),
        say 'Yes?', then record until silence.
        Returns (audio, sample_rate). Returns empty array if stopped.
        """
        # ── Phase 1: single stream handles both wake word and clap ───────────
        triggered = threading.Event()

        # Clap detection state — only mutated from the callback thread
        clap = _ClapState()

        def wake_callback(indata, frames, time_info, status):
            if self._stop_event.is_set():
                raise sd.CallbackStop()

            chunk = indata.copy().squeeze().astype(np.float32)
            now = time.monotonic()

            # ── Clap detection ────────────────────────────────────────────
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if self.on_level is not None:
                self.on_level(rms)
            is_loud = rms >= CLAP_ENERGY_THRESHOLD

            if is_loud and not clap.in_clap:
                clap.in_clap = True
                clap.duration_ms = _BLOCK_MS
                if clap.first_time is None:
                    clap.first_time = now
                else:
                    gap_ms = (now - clap.first_time) * 1000
                    if CLAP_MIN_GAP_MS <= gap_ms <= CLAP_MAX_GAP_MS:
                        # Valid double-clap
                        clap.in_clap = False
                        clap.duration_ms = 0.0
                        clap.first_time = None
                        print("👏 Double clap detected!")
                        triggered.set()
                        raise sd.CallbackStop()
                    elif gap_ms > CLAP_MAX_GAP_MS:
                        clap.first_time = now

            elif is_loud and clap.in_clap:
                clap.duration_ms += _BLOCK_MS
                if clap.duration_ms > CLAP_MAX_DURATION_MS:
                    # Too long — not a clap (speech, music, etc.)
                    clap.in_clap = False
                    clap.duration_ms = 0.0
                    clap.first_time = None

            elif not is_loud and clap.in_clap:
                clap.in_clap = False
                clap.duration_ms = 0.0

            # Expire first-clap timestamp if gap window has passed
            if clap.first_time and (now - clap.first_time) * 1000 > CLAP_MAX_GAP_MS + 300:
                clap.first_time = None

            # ── Wake word detection ───────────────────────────────────────
            if self.detector.process(chunk):
                self.detector.reset()
                triggered.set()
                raise sd.CallbackStop()

        with sd.InputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype=AUDIO_DTYPE,
            blocksize=CHUNK_SAMPLES,
            callback=wake_callback,
        ):
            while not triggered.is_set() and not self._stop_event.is_set():
                triggered.wait(timeout=0.05)

        if self._stop_event.is_set():
            return np.array([], dtype=np.float32), AUDIO_SAMPLE_RATE

        if self.on_triggered is not None:
            with contextlib.suppress(Exception):
                self.on_triggered()

        # ── Acknowledge (blocking so mic doesn't capture this) ────────────
        _speak_sync("Yes?")

        # ── Phase 2: record command with VAD ─────────────────────────────
        command_frames: list[np.ndarray] = []
        silence_chunks = {"n": 0}
        chunk_count = {"n": 0}
        done = threading.Event()

        silence_limit = int(VAD_SILENCE_SECONDS * AUDIO_SAMPLE_RATE / CHUNK_SAMPLES)
        max_chunks = int(MAX_COMMAND_SECONDS * AUDIO_SAMPLE_RATE / CHUNK_SAMPLES)

        def record_callback(indata, frames, time_info, status):
            if self._stop_event.is_set():
                raise sd.CallbackStop()

            chunk = indata.copy().squeeze().astype(np.float32)
            command_frames.append(chunk)
            chunk_count["n"] += 1

            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if self.on_level is not None:
                self.on_level(rms)
            if rms < VAD_ENERGY_THRESHOLD:
                silence_chunks["n"] += 1
            else:
                silence_chunks["n"] = 0

            # Stop when: silence long enough (and we have some audio) or hit time cap
            enough_audio = chunk_count["n"] > 5
            if (silence_chunks["n"] >= silence_limit and enough_audio) \
                    or chunk_count["n"] >= max_chunks:
                done.set()
                raise sd.CallbackStop()

        with sd.InputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype=AUDIO_DTYPE,
            blocksize=CHUNK_SAMPLES,
            callback=record_callback,
        ):
            done.wait(timeout=MAX_COMMAND_SECONDS + 5)

        if not command_frames:
            return np.array([], dtype=np.float32), AUDIO_SAMPLE_RATE

        audio = np.concatenate(command_frames)

        # Discard if it's too short to be a real command (< 0.3s)
        if audio.size < int(AUDIO_SAMPLE_RATE * 0.3):
            return np.array([], dtype=np.float32), AUDIO_SAMPLE_RATE

        return audio, AUDIO_SAMPLE_RATE
