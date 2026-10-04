# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Jarvis is a local macOS voice-activated AI assistant. It transcribes audio locally via whisper.cpp, classifies intent via regex fast-paths or Ollama (llama3.2), executes macOS actions, and responds via the native `say` command. Everything runs offline.

## Running the Project

```bash
pip install -r requirements.txt

# Push-to-talk mode (hold Space to speak)
python jarvis.py

# Always-on daemon mode (wake word or double clap)
python daemon.py
```

**Prerequisites:**
- Ollama running with `llama3.2:latest` (auto-started if available)
- whisper-cli at `/opt/homebrew/bin/whisper-cli`
- Whisper model at `~/whisper_models/ggml-base.en.bin`

No build step, no test suite, no linter configuration.

## Two Entry Points

**`jarvis.py`** — Push-to-talk: hold Space, speak, release. Simple loop with no threading.

**`daemon.py`** — Always-on background process. Activates via wake word (openWakeWord, default: "alexa") **or** double clap (within 700ms). Uses `ContinuousListener` + `ClapTrigger` running concurrently. A `JarvisState` state machine (`core/state_machine.py`) prevents overlapping activations — clap triggers are ignored while Jarvis is busy.

## Architecture

**Request flow:** trigger → audio record → whisper.cpp transcription (`core/stt/whisper_cpp.py`) → intent routing (`core/router.py`) → [agent pipeline or direct] → action execution (`core/executor.py`) → TTS response (`audio/tts.py`)

### Routing (core/router.py)
Three-tier routing:
1. **Fast-path** — regex/string matching for play, open, volume, memory queries ("play that again"). Zero LLM cost.
2. **Multi-step detection** — compound commands ("open Safari and then play Mozart") route to `{"tool": "__agent__"}`.
3. **LLM fallback** — `core/brain_local.py` via Ollama.

### Agent Pipeline (core/agent.py)
Handles multi-step commands. Calls a structured JSON planner LLM, validates the plan via `core/plan_validator.py` (tool allowlist, max 5 steps, no shell commands), executes each step through the executor, and verifies each result via `core/verifier.py` with one retry on retryable failures. Speaks progress updates between steps.

### Brain (core/brain_local.py)
Sends transcribed text to Ollama with a JSON-response system prompt. Returns `{"tool": "app"|"music"|"browser"|"shortcut"|"system"|null, ...}`. Configurable personalities via `PERSONALITY_MODE` in `config.py`: `"siri"`, `"smooth"`, `"professional"`, `"chill"`.

### Executor (core/executor.py)
Dispatches router output to the correct tool module. Returns `{ok, message, code, action_type, retryable, data}`.

### Tools (tools/)
Each tool is self-contained:
- `apps.py` — `open -a` + AppleScript verification, alias resolution
- `music.py` — delegates to `music/playback.py` (Apple Music via search in `music/search.py`; artist aliases in `music/artist_aliases.json`)
- `browser.py` — `webbrowser` module + site shortcuts + Google fallback; URL sanitization per security policy
- `system.py` — volume/lock/sleep/battery via AppleScript and `pmset`
- `shortcuts.py` — macOS Shortcuts via `shortcuts` CLI

### Security (security/)
`policy.py` loads `security/policy.json` and merges with hardcoded defaults. Controls:
- Which tools require voice confirmation before execution (`confirm_tools`)
- Blocked URL patterns (localhost, RFC-1918 ranges, `file://`)
- Tracking param stripping (`utm_*`, `gclid`, `fbclid`)
- Tool risk levels: `system` = low, `browser/app/music/open` = medium, `shortcut` = high

### Services (services/)
Thin wrappers isolating external dependencies:
- `applescript.py` — runs `osascript` subprocess calls
- `ollama_service.py` — manages Ollama lifecycle (health check, auto-start)

### Memory (memory/)
`context.py` maintains last 10 messages and action state (`last_song`, `last_app`, `last_browser_target`, `last_shortcut`, `last_action`) in `memory/context.json`. All actions are audit-logged to `memory/actions.json` with timestamps.

## Configuration

All tunables are in `config.py`:
- `WHISPER_MODEL`, `WHISPER_BIN` — STT paths
- `OLLAMA_MODEL`, `OLLAMA_URL`, `OLLAMA_TIMEOUT` — LLM settings
- `TTS_VOICE`, `TTS_RATE` — macOS say settings
- `PERSONALITY_MODE` — controls Ollama system prompt tone
- `AUDIO_SAMPLE_RATE` — 16kHz, must match whisper.cpp expectation
- `WAKE_WORD_MODEL`, `WAKE_WORD_THRESHOLD` — openWakeWord settings (daemon mode)
- `CLAP_ENERGY_THRESHOLD`, `CLAP_MAX_GAP_MS` — double-clap detection tuning
- `AGENT_MAX_STEPS` — hard cap on multi-step plan length (default: 5)

`.env` contains `OPENAI_API_KEY` — present but not used (Ollama is the active LLM).
