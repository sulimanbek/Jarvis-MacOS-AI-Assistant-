import os


def expand(path: str) -> str:
    return os.path.expanduser(path)


# ---------- WHISPER ----------
WHISPER_MODEL = expand("~/whisper_models/ggml-base.en.bin")
WHISPER_BIN = expand("/opt/homebrew/bin/whisper-cli")


# ---------- AUDIO ----------
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_DTYPE = "float32"


# ---------- TTS ----------
TTS_VOICE = "Samantha"
TTS_RATE = 150
# Samantha is the clearest/smoothest of the compact voices installed on this
# Mac. For a real step up in naturalness, download an Enhanced/Premium voice
# via System Settings -> Accessibility -> Spoken Content -> System Voice,
# then set TTS_VOICE to its exact name (e.g. "Ava (Premium)").
#Daniel
#Karen

# ---------- OLLAMA ----------
OLLAMA_MODEL = "llama3.2:latest"   #quen2.5:7b
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 25
OLLAMA_RETRY_ATTEMPTS = 2
OLLAMA_RETRY_BACKOFF_SECONDS = 0.75


# ---------- EXECUTION ----------
SUBPROCESS_TIMEOUT = 12


# ---------- PERSONALITY ----------
PERSONALITY_MODE = "siri"
# options: smooth, siri, professional, chill


# ---------- FILES ----------
ACTIONS_LOG_FILE = expand("memory/actions.json")
CONTEXT_FILE_PATH = expand("memory/context.json")


# ---------- CLAP TRIGGER ----------
CLAP_ENERGY_THRESHOLD = 0.25    # RMS level that counts as a clap (0.0–1.0)
CLAP_MAX_DURATION_MS  = 200     # Clap must end within this many ms (filters speech)
CLAP_MIN_GAP_MS       = 150     # Min gap between first and second clap
CLAP_MAX_GAP_MS       = 700     # Max gap between first and second clap


# ---------- AGENT ----------
AGENT_MAX_STEPS = 5             # Hard cap on multi-step plan length


# ---------- WAKE WORD ----------
# Pre-trained models (no download needed): alexa, hey_mycroft, hey_rhasspy, ok_nabu
# Custom "hey_jarvis" model: train one at github.com/dscripka/openWakeWord
WAKE_WORD_MODEL = "alexa"
WAKE_WORD_THRESHOLD = 0.5       # 0.0–1.0 — raise to reduce false triggers


# ---------- CLAUDE BRAIN / HUD (ui-bridge) ----------
# Who answers requests the regex fast-path can't handle:
#   "claude" — Claude via ui-bridge, falling back to Ollama if the bridge is down
#   "local"  — Ollama only (fully offline; the bridge is never contacted)
# Override without editing this file: JARVIS_BRAIN=local python daemon.py
BRAIN_MODE = os.environ.get("JARVIS_BRAIN", "claude").strip().lower()

# The bridge's private channel for this process. The token file is written by
# the bridge on each start (owner-only) and read here on each connect.
BRIDGE_URL = os.environ.get("JARVIS_BRIDGE_URL", "ws://127.0.0.1:8787/core")
# In "local" mode Claude is never used, so Python only reports to the HUD over
# this events-only channel — the bridge starts no Claude session for it.
BRIDGE_EVENTS_URL = os.environ.get("JARVIS_BRIDGE_EVENTS_URL", "ws://127.0.0.1:8787/events")
BRIDGE_TOKEN_FILE = expand("~/.jarvis/bridge-token")

CLAUDE_TIMEOUT = 45             # seconds to wait for a whole Claude turn
CLAUDE_CONNECT_TIMEOUT = 2      # seconds to wait when connecting to the bridge
CLAUDE_RETRY_COOLDOWN = 15      # after a failure, don't retry the bridge for this long

# Show state, transcripts and replies on the HUD (silently skipped if it's not running)
HUD_EVENTS = True


# ---------- GENERAL ----------
DEBUG = True