import subprocess
import time

import requests

from config import (
    OLLAMA_MODEL,
    OLLAMA_RETRY_ATTEMPTS,
    OLLAMA_RETRY_BACKOFF_SECONDS,
    OLLAMA_TIMEOUT,
    OLLAMA_URL,
)


def _base_url() -> str:
    return OLLAMA_URL.replace("/api/chat", "").replace("/api/generate", "")


def is_ollama_running(timeout: int = 2) -> bool:
    try:
        response = requests.get(_base_url(), timeout=timeout)
        return response.status_code in (200, 404)
    except requests.RequestException:
        return False


def start_ollama() -> bool:
    try:
        subprocess.Popen(
            ["open", "-a", "Ollama"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        print(f"❌ Failed to start Ollama app: {e}")
        return False


def ensure_ollama_running(wait_seconds: int = 15) -> bool:
    if is_ollama_running():
        return True

    print("🧠 Ollama is not running. Starting it...")
    if not start_ollama():
        return False

    for _ in range(wait_seconds):
        if is_ollama_running():
            print("✅ Ollama is now running.")
            return True
        time.sleep(1)

    print("❌ Ollama did not start in time.")
    return False


def ask_ollama(messages: list[dict], model: str | None = None, timeout: int | None = None) -> str:
    model = model or OLLAMA_MODEL
    timeout = timeout or OLLAMA_TIMEOUT

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "num_predict": 120,
        },
    }

    for attempt in range(1, OLLAMA_RETRY_ATTEMPTS + 1):
        try:
            response = requests.post(f"{_base_url()}/api/chat", json=payload, timeout=timeout)

            if response.status_code == 200:
                data = response.json()
                return (data.get("message", {}).get("content") or "").strip()

            if response.status_code == 404:
                # /api/chat isn't available on this Ollama version — fall back below.
                break

            print("🧠 /api/chat raw:", response.text[:300])
            response.raise_for_status()

        except (requests.RequestException, ValueError) as e:
            print(f"⚠️ /api/chat error (attempt {attempt}/{OLLAMA_RETRY_ATTEMPTS}): {e}")
            if attempt < OLLAMA_RETRY_ATTEMPTS:
                time.sleep(OLLAMA_RETRY_BACKOFF_SECONDS * attempt)

    for attempt in range(1, OLLAMA_RETRY_ATTEMPTS + 1):
        try:
            prompt = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
            )

            fallback_payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.5,
                    "num_predict": 120,
                },
            }

            response = requests.post(f"{_base_url()}/api/generate", json=fallback_payload, timeout=timeout)
            response.raise_for_status()

            data = response.json()
            return (data.get("response") or "").strip()

        except (requests.RequestException, ValueError) as e:
            print(f"❌ Ollama request error (attempt {attempt}/{OLLAMA_RETRY_ATTEMPTS}): {e}")
            if attempt < OLLAMA_RETRY_ATTEMPTS:
                time.sleep(OLLAMA_RETRY_BACKOFF_SECONDS * attempt)

    return ""