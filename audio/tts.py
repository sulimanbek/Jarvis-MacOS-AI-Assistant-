import contextlib
import hashlib
import os
import random
import re
import subprocess
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import RLock, Thread

import requests

from config import (
    BRAIN_MODE,
    ELEVENLABS_BASE_URL,
    ELEVENLABS_MODEL,
    ELEVENLABS_SIMILARITY,
    ELEVENLABS_SPEED,
    ELEVENLABS_STABILITY,
    ELEVENLABS_TIMEOUT,
    ELEVENLABS_VOICE_ID,
    SUBPROCESS_TIMEOUT,
    TTS_ENGINE,
    TTS_RATE,
    TTS_VOICE,
    VOICE_CACHE_DIR,
)

_ACK_PHRASES = [
    "On it.",
    "Sure.",
    "Got it.",
    "Working on that.",
    "Right away.",
    "One moment.",
]


# Re-entrant: the ElevenLabs path falls back to the macOS voice while holding it.
_tts_lock = RLock()


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


_player: subprocess.Popen | None = None


def _stop_existing_speech():
    global _player
    with contextlib.suppress(Exception):
        subprocess.run(
            ["killall", "say"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    proc, _player = _player, None
    if proc is not None and proc.poll() is None:
        with contextlib.suppress(Exception):
            proc.terminate()


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


# ── ElevenLabs ──────────────────────────────────────────────────────────────

# Phrases that never change, so their audio is kept and replayed instead of
# being paid for and waited on every time.
_CACHEABLE = set(_ACK_PHRASES) | {"Yes?", "Jarvis online.", "Goodbye.", "Done."}

# After a failed request the Mac voice is used for a while rather than making
# every reply wait for a timeout. An auth failure lasts for the whole session.
_COOLDOWN_SECONDS = 60.0
_cloud_down_until = 0.0
_warned: set[str] = set()


def _elevenlabs_key() -> str:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def tts_engine() -> str:
    """Which voice will speak right now: "elevenlabs" or "system"."""
    if TTS_ENGINE == "system" or not _elevenlabs_key():
        return "system"
    if TTS_ENGINE == "auto" and BRAIN_MODE == "local":
        return "system"
    return "elevenlabs"


def describe_engine() -> str:
    """One line for the startup banner, saying which voice is active and why."""
    if tts_engine() == "elevenlabs":
        return "ElevenLabs (replies are sent to ElevenLabs to be spoken; falls back to the Mac voice)"
    if TTS_ENGINE == "system":
        return f"macOS voice {TTS_VOICE} (JARVIS_TTS=system)"
    if not _elevenlabs_key():
        return f"macOS voice {TTS_VOICE} (set ELEVENLABS_API_KEY in .env for a better voice)"
    return f"macOS voice {TTS_VOICE} (local mode stays offline; JARVIS_TTS=elevenlabs overrides)"


def _warn_once(kind: str, message: str) -> None:
    if kind not in _warned:
        _warned.add(kind)
        print(message)


def _prepare_cloud_text(text: str) -> str:
    """Light cleanup only: ElevenLabs reads acronyms and names correctly itself."""
    text = re.sub(r"^\s*Jarvis:\s*", "", (text or "").strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text


def _fetch_elevenlabs(text: str) -> bytes | None:
    """MP3 audio for `text`, or None on any failure (never raises)."""
    global _cloud_down_until
    key = _elevenlabs_key()
    if not key or time.monotonic() < _cloud_down_until:
        return None
    try:
        response = requests.post(
            f"{ELEVENLABS_BASE_URL}/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            params={"output_format": "mp3_44100_64"},
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": ELEVENLABS_MODEL,
                "voice_settings": {
                    "stability": ELEVENLABS_STABILITY,
                    "similarity_boost": ELEVENLABS_SIMILARITY,
                    "speed": ELEVENLABS_SPEED,
                },
            },
            timeout=ELEVENLABS_TIMEOUT,
        )
    except requests.RequestException as e:
        _cloud_down_until = time.monotonic() + _COOLDOWN_SECONDS
        _warn_once("net", f"⚠️ ElevenLabs unreachable ({type(e).__name__}) — using the Mac voice for a minute.")
        return None

    if response.status_code == 200 and response.content:
        return response.content

    if response.status_code in (401, 403):
        _cloud_down_until = float("inf")
        _warn_once("auth", "⚠️ ElevenLabs rejected the API key — using the Mac voice. Check ELEVENLABS_API_KEY in .env.")
    elif response.status_code in (402, 429):
        _cloud_down_until = time.monotonic() + 5 * _COOLDOWN_SECONDS
        _warn_once("quota", "⚠️ ElevenLabs is out of credits or rate-limited — using the Mac voice for a few minutes.")
    else:
        _cloud_down_until = time.monotonic() + _COOLDOWN_SECONDS
        _warn_once("http", f"⚠️ ElevenLabs returned {response.status_code} — using the Mac voice for a minute.")
    return None


def _cache_path(text: str) -> Path:
    digest = hashlib.sha256(f"{ELEVENLABS_VOICE_ID}|{ELEVENLABS_MODEL}|{text}".encode()).hexdigest()[:24]
    return Path(VOICE_CACHE_DIR) / f"{digest}.mp3"


def _audio_file(text: str, cacheable: bool) -> tuple[Path, bool] | None:
    """A playable file for `text` and whether it is temporary (to delete after)."""
    path = _cache_path(text) if cacheable else None
    if path is not None and path.is_file() and path.stat().st_size > 0:
        return path, False

    data = _fetch_elevenlabs(text)
    if not data:
        return None

    if path is not None:
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            return path, False

    fd, name = tempfile.mkstemp(prefix="jarvis-", suffix=".mp3")  # created owner-only
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return Path(name), True


def _play_file(path: Path) -> bool:
    global _player
    try:
        proc = subprocess.Popen(["afplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    _player = proc
    proc.wait()
    return True


def _run_elevenlabs(text: str) -> bool:
    """Speak with ElevenLabs. False means nothing was spoken and the caller should use the Mac voice."""
    cleaned = _prepare_cloud_text(text)
    if not cleaned:
        return True
    chunks = _chunk_for_speech(cleaned, max_len=240)
    cacheable = cleaned in _CACHEABLE

    with _tts_lock:
        _stop_existing_speech()
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            ready: Future[tuple[Path, bool] | None] | None = pool.submit(_audio_file, chunks[0], cacheable)
            for i in range(len(chunks)):
                assert ready is not None
                audio = ready.result()
                # Fetch the next sentence while this one plays, so there is no gap.
                ready = pool.submit(_audio_file, chunks[i + 1], False) if i + 1 < len(chunks) else None
                if audio is None or not _play_file(audio[0]):
                    if audio is not None and audio[1]:
                        audio[0].unlink(missing_ok=True)
                    if i == 0:
                        return False
                    _run_say(" ".join(chunks[i:]))  # finish the reply in the Mac voice
                    return True
                if audio[1]:
                    audio[0].unlink(missing_ok=True)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    return True


def _run_speech(text: str):
    """Speak with whichever voice is active, falling back to the Mac voice."""
    if tts_engine() == "elevenlabs" and _run_elevenlabs(text):
        return
    _run_say(text)


def speak_sync(text: str):
    """Blocking version, for the moments the microphone must not hear Jarvis."""
    if text and text.strip():
        _run_speech(text)


def speak(text: str):
    if not text or not text.strip():
        return

    Thread(target=_run_speech, args=(text,), daemon=True).start()


def speak_ack():
    """Fire a random quick acknowledgment phrase before starting execution."""
    speak(random.choice(_ACK_PHRASES))