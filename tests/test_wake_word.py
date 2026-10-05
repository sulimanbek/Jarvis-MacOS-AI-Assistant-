import numpy as np

from audio import wake_word
from audio.wake_word import CHUNK_SAMPLES, WakeWordDetector, to_pcm16


def test_float_audio_is_scaled_to_int16():
    out = to_pcm16(np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32))
    assert out.dtype == np.int16
    assert out.tolist() == [0, 16384, -16384, 32767, -32768]


def test_loud_float_audio_is_clipped_not_wrapped():
    out = to_pcm16(np.array([2.0, -2.0], dtype=np.float32))
    assert out.tolist() == [32767, -32768]


def test_int16_audio_passes_through_unchanged():
    a = np.array([1, -2, 300], dtype=np.int16)
    assert to_pcm16(a).tolist() == [1, -2, 300]


class FakeModel:
    def __init__(self, *a, **k):
        self.seen = []
        self.score = 0.0

    def predict(self, x):
        self.seen.append(x)
        return {"hey_jarvis": self.score}

    def reset(self):
        pass


def _detector(monkeypatch):
    monkeypatch.setattr(wake_word, "Model", FakeModel)
    return WakeWordDetector("hey_jarvis", 0.5)


def test_detector_feeds_the_model_int16_not_raw_floats(monkeypatch):
    det = _detector(monkeypatch)
    chunk = (np.sin(np.linspace(0, 40, CHUNK_SAMPLES)) * 0.4).astype(np.float32)
    det.process(chunk)
    fed = det.model.seen[0]
    assert fed.dtype == np.int16
    # Real speech-level audio must arrive at real int16 magnitudes.
    assert np.abs(fed).max() > 10000


def test_detector_fires_at_or_above_the_threshold(monkeypatch):
    det = _detector(monkeypatch)
    chunk = np.zeros(CHUNK_SAMPLES, dtype=np.float32)
    det.model.score = 0.49
    assert det.process(chunk) is False
    det.model.score = 0.5
    assert det.process(chunk) is True
