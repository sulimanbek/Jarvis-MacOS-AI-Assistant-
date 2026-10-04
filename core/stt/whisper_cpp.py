import os
import subprocess
import tempfile
from pathlib import Path

import soundfile as sf

from config import SUBPROCESS_TIMEOUT, WHISPER_BIN, WHISPER_MODEL


def transcribe(audio_f32, sample_rate: int = 16000) -> str:
    """
    Transcribe in-memory float32 audio using local whisper.cpp.

    Args:
        audio_f32: numpy float32 array in range [-1, 1]
        sample_rate: audio sample rate

    Returns:
        Transcribed text as a stripped string.
    """
    whisper_bin = os.path.expanduser(WHISPER_BIN)
    whisper_model = os.path.expanduser(WHISPER_MODEL)

    if not os.path.isfile(whisper_bin):
        raise FileNotFoundError(f"Whisper binary not found: {whisper_bin}")

    if not os.path.isfile(whisper_model):
        raise FileNotFoundError(f"Whisper model not found: {whisper_model}")

    if audio_f32 is None or getattr(audio_f32, "size", 0) == 0:
        return ""

    with tempfile.TemporaryDirectory() as temp_dir:
        wav_path = os.path.join(temp_dir, "input.wav")
        out_base = os.path.join(temp_dir, "output")
        txt_path = out_base + ".txt"

        sf.write(wav_path, audio_f32, sample_rate)

        cmd = [
            whisper_bin,
            "-m", whisper_model,
            "-f", wav_path,
            "-otxt",
            "-of", out_base,
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=SUBPROCESS_TIMEOUT * 5,
            )
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            raise RuntimeError(f"whisper.cpp transcription failed: {stderr or e}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"whisper.cpp transcription timed out: {e}") from e

        if not Path(txt_path).exists():
            raise RuntimeError("whisper.cpp did not produce a transcription file.")

        with open(txt_path, encoding="utf-8") as f:
            return f.read().strip()