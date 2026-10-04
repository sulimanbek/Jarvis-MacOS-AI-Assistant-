import numpy as np
from openwakeword.model import Model

# openwakeword requires 80ms chunks at 16kHz
CHUNK_SAMPLES = 1280


class WakeWordDetector:
    def __init__(self, model_name: str, threshold: float):
        self.model = Model(wakeword_models=[model_name], inference_framework="onnx")
        self.threshold = threshold

    def process(self, chunk: np.ndarray) -> bool:
        predictions = self.model.predict(chunk)
        return any(score >= self.threshold for score in predictions.values())

    def reset(self):
        self.model.reset()
