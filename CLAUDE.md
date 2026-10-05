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

No build step. Tests: `pytest` (config in `pyproject.toml`); lint: `ruff`.

**Everything at once (Claude brain + HUD + Python core):** double-click `Jarvis.command` (or
`Jarvis (Local).command`), or run `scripts/start_all.sh`. It refuses to start over an old instance or
a busy port 8787/5173 unless you confirm; `--check` only checks.
`scripts/autostart.sh install|uninstall|status|start` manages a LaunchAgent (`com.jarvis.assistant`) that opens
Terminal with `Jarvis.command` ~15s after login. It goes through Terminal on purpose: a background launchd
process usually can't get microphone/Automation permission.
(`--ptt` push-to-talk, `--writes` allow Claude to act in the browser, `--local` HUD with
the local Ollama brain only, `--local --no-hud` headless and fully offline). Needs Node 20+
and a Claude Code login for the Claude brain; `--local --no-hud` needs neither.

## Two Entry Points

**`jarvis.py`** — Push-to-talk: hold RIGHT OPTION, speak, release. Simple loop with no threading.

**`daemon.py`** — Always-on background process. Activates via wake word (openWakeWord, default: "hey_jarvis") **or** double clap (within 700ms). Uses `ContinuousListener` + `ClapTrigger` running concurrently. A `JarvisState` state machine (`core/state_machine.py`) prevents overlapping activations — clap triggers are ignored while Jarvis is busy.

## Architecture

**Request flow:** trigger → audio record → whisper.cpp transcription (`core/stt/whisper_cpp.py`) → intent routing (`core/router.py`) → [agent pipeline or direct] → action execution (`core/executor.py`) → TTS response (`audio/tts.py`)

### Routing (core/router.py)
Three-tier routing:
1. **Fast-path** — regex/string matching for play, open, volume, memory queries ("play that again"). Zero LLM cost.
2. **Multi-step detection** — compound commands ("open Safari and then play Mozart") route to `{"tool": "__agent__"}`.
3. **LLM fallback** — Claude via `core/brain_claude.py` (when `BRAIN_MODE = "claude"` and the bridge is up), otherwise `core/brain_local.py` via Ollama.

### Agent Pipeline (core/agent.py)
Handles multi-step commands. Calls a structured JSON planner LLM, validates the plan via `core/plan_validator.py` (tool allowlist, max 5 steps, no shell commands), executes each step through the executor, and verifies each result via `core/verifier.py` with one retry on retryable failures. Speaks progress updates between steps.

### Claude brain + HUD (core/brain_claude.py, core/bridge_client.py, ui-bridge/)
`ui-bridge/` is a vendored, hardened copy of adewaskar/jarvis (MIT; see `ui-bridge/NOTICE.md`):
a Node bridge running the Claude Agent SDK plus a React/Three.js holographic HUD.

- The router's LLM fallback tries **Claude first** (`BRAIN_MODE = "claude"`), then Ollama if the
  bridge is down or Claude's turn fails. The regex fast-path and multi-step agent stay local and
  never touch Claude. `BRAIN_MODE = "local"` (or `JARVIS_BRAIN=local`) never asks Claude; it still reports to the HUD over
  the bridge's token-authenticated `/events` channel, which starts no Claude session.
- Python connects to the bridge's private `/core` WebSocket with a token the bridge writes
  (owner-only) to `~/.jarvis/bridge-token`. `BridgeClient.ask()` sends a request and streams
  back Claude's answer; `emit()` pushes state/heard/reply events that the HUD displays.
  The HUD runs display-only (`VITE_CORE_MODE=1`): Python keeps the mic, whisper and `say`.
  `core/level_stream.py` sends your mic level (one 0-1 number, ~15/s, from its own thread so the
  audio callback never blocks) as droppable `level` events, which never dial or wait on the lock.
- Claude can act on the Mac through the bridge's `mac_action` tool, which calls back into Python
  (`core/mac_actions.py`). Those calls go through the same validator and executor, but are held to
  a stricter bar than your voice: `browser`/`open`/`shortcut` always need a spoken yes, and
  `clipboard_read`/`screenshot` are refused (a model can be steered by text it read).
- Bridge hardening lives in `ui-bridge/bridge/server.mjs` (loopback bind, origin/referer checks,
  sandboxed agent files, opt-in MCP servers, confirmation + `disallowedTools` for effectful tools).
  `ui-bridge/README.md` has a "Local hardening" section.

### Brain (core/brain_local.py)
Sends transcribed text to Ollama with a JSON-response system prompt. Returns `{"tool": "app"|"music"|"browser"|"shortcut"|"system"|null, ...}`. Configurable personalities via `PERSONALITY_MODE` in `config.py`: `"siri"`, `"smooth"`, `"professional"`, `"chill"`.

### Local connections (tools/, core/system_actions.py)
New abilities are added once, in the `SYSTEM_ACTIONS` registry (`core/system_actions.py`), which
the executor, planner prompts and plan validator all derive from. Music transport (`tools/media.py`,
Apple Music only, never launches Music), read-only Calendar (`tools/calendar.py`) and Mail
(`tools/mail.py`) go through AppleScript; spoken phrases for them are in `router._route_apps`
(anchored regexes, so ordinary sentences aren't taken for commands, and anything with an editing
verb is left alone). Calendar, mail, clipboard and screenshot are in
`mac_actions.MODEL_BLOCKED_SYSTEM_ACTIONS`: answered locally, never handed to Claude.
Shortcuts: `tools/shortcuts.match_shortcut` maps a spoken sentence to an installed shortcut name;
the Shortcuts app only runs an exact name.

### Voice (audio/tts.py)
`speak()` runs `_run_speech` on a thread: ElevenLabs when `ELEVENLABS_API_KEY` is set (in `.env`) and
`tts_engine()` allows it, otherwise (or on any failure) the macOS `say` voice. `TTS_ENGINE` is `auto`
(ElevenLabs unless the brain is `local`, which stays offline), `elevenlabs`, or `system`. Audio is
fetched a sentence ahead while the previous one plays and played with `afplay`; after a failed request
the Mac voice is used for 60s (for the whole session on a 401/403). Only the fixed phrases in
`_CACHEABLE` are cached (`~/.jarvis/voice-cache`); replies are never written to disk beyond a temp file
deleted after playback. The wake-word "Yes?" goes through the same path (`speak_sync`). Tests never
touch the network (conftest clears the key); `.env.example` documents the setting.

### Wake word (audio/wake_word.py)
openWakeWord needs 16-bit PCM sample values; the mic stream is float32 in -1..1, so
`to_pcm16` scales it. Without that the model scored 0.00 on everything and only the clap worked.
Default model is the bundled `hey_jarvis`.

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
- `BRAIN_MODE`, `BRIDGE_URL`, `BRIDGE_TOKEN_FILE` — Claude/HUD bridge (see above)
- `CLAUDE_TIMEOUT`, `CLAUDE_CONNECT_TIMEOUT`, `CLAUDE_RETRY_COOLDOWN` — bridge timing; after a
  failure the bridge isn't retried for the cooldown, so a missing bridge costs one short attempt
- `HUD_EVENTS` — turn HUD updates on/off

`.env` contains `OPENAI_API_KEY` — present but not used (Ollama is the active LLM).
