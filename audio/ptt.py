import threading

import numpy as np
import sounddevice as sd
from pynput import keyboard

from config import AUDIO_CHANNELS, AUDIO_DTYPE, AUDIO_SAMPLE_RATE

DEFAULT_TRIGGER_KEY = keyboard.Key.alt_r


def record_push_to_talk(trigger_key=DEFAULT_TRIGGER_KEY):
    """
    Hold the trigger key to record, release to stop.

    Returns:
        tuple[np.ndarray, int]:
            audio as float32 numpy array, sample rate
    """
    frames = []
    recording = threading.Event()

    def callback(indata, frames_count, time_info, status):
        if status:
            print(f"⚠️ Audio status: {status}")
        if recording.is_set():
            frames.append(indata.copy())

    def on_press(key):
        if key == trigger_key and not recording.is_set():
            print("🎙️ Listening... (hold RIGHT option, release to stop)")
            recording.set()

    def on_release(key):
        if key == trigger_key and recording.is_set():
            recording.clear()
            return False

    try:
        with sd.InputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype=AUDIO_DTYPE,
            callback=callback,
        ), keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    except Exception as e:
        print(f"❌ Push-to-talk error: {e}")
        return np.array([], dtype=np.float32), AUDIO_SAMPLE_RATE

    if not frames:
        return np.array([], dtype=np.float32), AUDIO_SAMPLE_RATE

    audio = np.concatenate(frames, axis=0).squeeze().astype(np.float32)

    # Ignore accidental very short taps
    min_samples = int(AUDIO_SAMPLE_RATE * 0.15)
    if audio.size < min_samples:
        return np.array([], dtype=np.float32), AUDIO_SAMPLE_RATE

    return audio, AUDIO_SAMPLE_RATE