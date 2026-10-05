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


# ---------- CONVERSATION ----------
# After Jarvis answers, keep listening for a reply without needing "hey jarvis" again.
# It goes back to waiting for the wake word after FOLLOWUP_SECONDS of quiet, or when you say
# "thanks", "that's all", "never mind" or "stop".
# Turn it off: JARVIS_FOLLOWUP=0 python daemon.py
FOLLOWUP_ENABLED = os.environ.get("JARVIS_FOLLOWUP", "1").strip() != "0"
FOLLOWUP_SECONDS = 7           # how long to wait for you to start talking
FOLLOWUP_ONSET_ENERGY = 0.02   # how loud counts as you starting to speak (room noise is ~0.005)
FOLLOWUP_ONSET_CHUNKS = 3      # ...for this many 80ms chunks in a row
FOLLOWUP_MAX_TURNS = 25        # safety cap on back-to-back follow-ups
FOLLOWUP_SETTLE_SECONDS = 0.4  # pause after Jarvis stops talking so the mic doesn't hear the tail


# ---------- VOICE ----------
# Which voice speaks:
#   "auto"       — ElevenLabs when ELEVENLABS_API_KEY is set (in .env) and the brain isn't
#                  "local"; otherwise the macOS voice above. Local mode stays fully offline.
#   "elevenlabs" — ElevenLabs whenever there is a key, even in local mode (replies are sent
#                  to ElevenLabs to be spoken)
#   "system"     — always the macOS voice (nothing leaves your Mac)
# Override without editing this file: JARVIS_TTS=system python daemon.py
TTS_ENGINE = os.environ.get("JARVIS_TTS", "auto").strip().lower()

# George: a warm British male voice, one of ElevenLabs' built-in voices. Any voice id from
# elevenlabs.io/app/voices works (JARVIS_VOICE_ID is shared with the bridge's settings).
ELEVENLABS_VOICE_ID = os.environ.get("JARVIS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL = "eleven_flash_v2_5"   # the low-latency model; "eleven_multilingual_v2" sounds a touch richer
ELEVENLABS_STABILITY = 0.45              # lower = more expressive, higher = steadier
ELEVENLABS_SIMILARITY = 0.75
ELEVENLABS_SPEED = 1.0
ELEVENLABS_TIMEOUT = 8                   # seconds to wait for audio before using the Mac voice
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
# Fixed phrases ("Yes?", "On it.") are saved here so they play instantly and cost nothing twice.
VOICE_CACHE_DIR = expand("~/.jarvis/voice-cache")


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
# Pre-trained models that ship with openWakeWord (no download needed):
#   hey_jarvis, alexa, hey_mycroft, hey_rhasspy, timer, weather
WAKE_WORD_MODEL = "hey_jarvis"
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