import numpy as np
from openwakeword.model import Model

# openwakeword requires 80ms chunks at 16kHz
CHUNK_SAMPLES = 1280


def to_pcm16(chunk: np.ndarray) -> np.ndarray:
    """
    openWakeWord wants 16-bit PCM sample values (-32768..32767).

    The microphone stream here is float32 in -1..1. Passed straight through, the
    model sees values a thousand times too quiet and scores 0.00 on everything,
    including its own wake word, so the wake word silently never fires.
    """
    if np.issubdtype(chunk.dtype, np.floating):
        return np.clip(chunk * 32768.0, -32768, 32767).astype(np.int16)
    return chunk.astype(np.int16, copy=False)


class WakeWordDetector:
    def __init__(self, model_name: str, threshold: float):
        self.model = Model(wakeword_models=[model_name], inference_framework="onnx")
        self.threshold = threshold

    def process(self, chunk: np.ndarray) -> bool:
        predictions = self.model.predict(to_pcm16(chunk))
        return any(score >= self.threshold for score in predictions.values())

    def reset(self):
        self.model.reset()
