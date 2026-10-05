"""
audio/utterance.py

Decides, chunk by chunk, when someone starts and stops speaking. Pure logic with
no audio hardware, so it can be tested with synthetic chunks.

Used for follow-ups: after Jarvis replies there is no wake word, so this waits a
short while for you to start talking, records until you stop, and gives up
quietly if you never do.
"""

from collections import deque

import numpy as np

WAITING = "waiting"
RECORDING = "recording"
DONE = "done"
TIMED_OUT = "timed_out"


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64)))) if chunk.size else 0.0


class UtteranceDetector:
    def __init__(
        self,
        *,
        onset_energy: float,
        silence_energy: float,
        onset_chunks: int,
        window_chunks: int,
        silence_chunks: int,
        max_chunks: int,
        preroll_chunks: int = 4,
    ):
        """
        onset_energy   RMS that counts as speech starting. Higher than silence_energy so a
                       fan or traffic doesn't start a recording.
        silence_energy RMS below which a chunk counts as quiet once recording.
        onset_chunks   consecutive loud chunks needed before it counts, so a click or a
                       cough doesn't.
        window_chunks  how long to wait for speech to start before giving up.
        silence_chunks quiet chunks in a row that end the utterance.
        max_chunks     hard cap on the recording length.
        preroll_chunks recent chunks kept from before the onset, so the first syllable
                       isn't clipped.
        """
        self.onset_energy = onset_energy
        self.silence_energy = silence_energy
        self.onset_chunks = onset_chunks
        self.window_chunks = window_chunks
        self.silence_chunks = silence_chunks
        self.max_chunks = max_chunks
        self.state = WAITING
        self.last_rms = 0.0
        self._preroll: deque[np.ndarray] = deque(maxlen=preroll_chunks)
        self._frames: list[np.ndarray] = []
        self._waited = 0
        self._loud_run = 0
        self._quiet_run = 0

    def feed(self, chunk: np.ndarray) -> str:
        """Process one chunk and return the new state. Once DONE or TIMED_OUT it stays there."""
        if self.state in (DONE, TIMED_OUT):
            return self.state

        self.last_rms = rms(chunk)

        if self.state == WAITING:
            self._waited += 1
            self._preroll.append(chunk)
            self._loud_run = self._loud_run + 1 if self.last_rms >= self.onset_energy else 0
            if self._loud_run >= self.onset_chunks:
                self.state = RECORDING
                self._frames = list(self._preroll)
                self._quiet_run = 0
            elif self._waited >= self.window_chunks:
                self.state = TIMED_OUT
            return self.state

        # RECORDING
        self._frames.append(chunk)
        self._quiet_run = self._quiet_run + 1 if self.last_rms < self.silence_energy else 0
        if self._quiet_run >= self.silence_chunks or len(self._frames) >= self.max_chunks:
            self.state = DONE
        return self.state

    def audio(self) -> np.ndarray:
        """The recorded speech, or an empty array if none was heard."""
        if self.state != DONE or not self._frames:
            return np.array([], dtype=np.float32)
        return np.concatenate(self._frames).astype(np.float32, copy=False)
