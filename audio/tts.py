import contextlib
import random
import re
import subprocess
from threading import Lock, Thread

from config import SUBPROCESS_TIMEOUT, TTS_RATE, TTS_VOICE

_ACK_PHRASES = [
    "On it.",
    "Sure.",
    "Got it.",
    "Working on that.",
    "Right away.",
    "One moment.",
]


_tts_lock = Lock()


def _expand_acronyms(text: str) -> str:
    # Speak short acronyms as letters (API -> A P I) for clearer pronunciation.
    return re.sub(
        r"\b([A-Z]{2,5})\b",
        lambda m: " ".join(m.group(1)),
        text,
    )


def _chunk_for_speech(text: str, max_len: int = 180) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if len(part) <= max_len:
            chunks.append(part)
            continue

        sub_parts = re.split(r"(?<=[,;:])\s+", part)
        for sub in sub_parts:
            sub = sub.strip()
            if not sub:
                continue
            if len(sub) <= max_len:
                chunks.append(sub)
            else:
                for i in range(0, len(sub), max_len):
                    chunks.append(sub[i:i + max_len].strip())

    return [c for c in chunks if c]


def _prepare_tts_text(text: str) -> str:
    text = (text or "").strip()

    if not text:
        return ""

    # Remove assistant label if present
    text = re.sub(r"^\s*Jarvis:\s*", "", text, flags=re.IGNORECASE)

    # Expand a few technical terms so speech sounds smoother
    replacements = {
        "PyCharm": "Pie charm",
        "macOS": "Mac oh ess",
        "GitHub": "Git hub",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = _expand_acronyms(text)

    # Clean awkward punctuation / spacing
    text = text.replace("&", " and ")
    text = text.replace("/", " ")
    text = text.replace("_", " ")
    text = text.replace("...", ", ")
    text = re.sub(r"\s+", " ", text).strip()

    # Add a slightly softer rhythm and avoid abrupt speech transitions.
    text = re.sub(r"\s*[-]\s*", ", ", text)
    text = re.sub(r",", ", ", text)
    text = re.sub(r";", "; ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Ensure sentence ending so voice doesn't cut off abruptly
    if not text.endswith((".", "!", "?")):
        text += "."

    return text


def _stop_existing_speech():
    with contextlib.suppress(Exception):
        subprocess.run(
            ["killall", "say"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _run_say(text: str):
    cleaned = _prepare_tts_text(text)
    if not cleaned:
        return

    with _tts_lock:
        try:
            _stop_existing_speech()

            rate = int(TTS_RATE) if TTS_RATE else 158
            chunks = _chunk_for_speech(cleaned)
            for chunk in chunks:
                cmd = ["say"]

                if TTS_VOICE:
                    cmd += ["-v", TTS_VOICE]

                cmd += ["-r", str(rate)]
                cmd.append(chunk)

                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=SUBPROCESS_TIMEOUT,
                )

        except Exception as e:
            print(f"❌ TTS error: {e}")


def speak(text: str):
    if not text or not text.strip():
        return

    Thread(target=_run_say, args=(text,), daemon=True).start()


def speak_ack():
    """Fire a random quick acknowledgment phrase before starting execution."""
    speak(random.choice(_ACK_PHRASES))