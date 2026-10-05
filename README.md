# Jarvis — Voice Assistant for macOS

A voice-activated assistant for macOS. It listens locally, handles common commands instantly without any AI call, and hands everything else to Claude. A holographic HUD shows what it's doing.

- **Local first.** Speech recognition (whisper.cpp), wake word, double-clap trigger, and the voice (`say`) all run on your Mac.
- **Fast commands cost nothing.** "Open Safari", "volume up", "play Starboy" are matched with regex and run in milliseconds, with no model involved.
- **Claude for the rest.** Anything the fast path can't match goes to Claude through a small Node bridge. If the bridge is down, Jarvis falls back to a local Ollama model, so it keeps working offline.
- **Acts on your Mac, with guardrails.** Claude can open apps, play music, change the volume and more, but only through Jarvis's own validator and security policy.

> Status: personal project. The Python core has a test suite; the HUD and the live voice path (wake word, clap, spoken confirmations) are tested by hand.

---

## How it works

```text
 wake word / double clap / hold-to-talk
              │
              ▼
   record  →  whisper.cpp (local STT)
              │
              ▼
         core/router.py
   ┌──────────┼──────────────────────┐
   ▼          ▼                      ▼
fast-path   multi-step agent     Claude (via bridge)  ──►  Ollama if bridge is down
 (regex)    (local planner)            │
   └──────────┼────────────────────────┘
              ▼
        core/executor.py  →  apps · music · browser · system · Shortcuts
              ▼
        macOS `say`  +  live events to the HUD
```

| Tier | Handles | Cost |
|---|---|---|
| **Fast-path** | play, open, volume, battery, reminders, notes, "play that again" | none |
| **Multi-step agent** | "open Safari and then play Mozart": plan is validated (allowlist, max 5 steps, no shell), run step by step, each step verified | local model |
| **Claude** | questions, conversation, anything unusual | your Claude usage |

The **HUD** (`ui-bridge/`) is a React + Three.js interface that runs display-only: it shows state, what was heard, replies, and anything Claude puts on screen. The Python process keeps the microphone and the voice.

---

## Requirements

- macOS, Python 3.11+
- [Ollama](https://ollama.com) with `llama3.2:latest` (local fallback and multi-step planner)
- `whisper-cli` at `/opt/homebrew/bin/whisper-cli` (`brew install whisper-cpp`) and the model `~/whisper_models/ggml-base.en.bin`
- For the Claude brain and HUD: **Node.js 20+**, Chrome or Edge, and a logged-in [Claude Code](https://docs.claude.com/en/docs/claude-code) (the bridge reuses that login; no API key)

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ui-bridge && npm install && cd ..     # optional: only for Claude + HUD
```

## Run

```bash
scripts/start_all.sh            # bridge + HUD + always-on Jarvis (wake word / double clap)
scripts/start_all.sh --ptt      # push-to-talk instead
scripts/start_all.sh --writes   # let Claude click/type/navigate in the browser (each asks first)
scripts/start_all.sh --local    # no bridge, no HUD: fully offline, Ollama only
```

Open `http://localhost:5173` in Chrome (the script does this), click **INITIALISE**, then clap twice or say the wake word (default: "alexa").

Without the launcher:

```bash
python daemon.py        # always-on
python jarvis.py        # push-to-talk
```

---

## Configuration

Everything is in `config.py`.

| Setting | Meaning |
|---|---|
| `BRAIN_MODE` | `"claude"` (default) or `"local"`. Also `JARVIS_BRAIN=local python daemon.py` |
| `BRIDGE_URL`, `BRIDGE_TOKEN_FILE` | Where the bridge's private channel is and where its token lives |
| `CLAUDE_TIMEOUT`, `CLAUDE_RETRY_COOLDOWN` | How long to wait for Claude; after a failure the bridge isn't retried for this long |
| `HUD_EVENTS` | Send live updates to the HUD |
| `WHISPER_MODEL`, `WHISPER_BIN` | Speech-to-text paths |
| `OLLAMA_MODEL`, `OLLAMA_URL` | Local model |
| `TTS_VOICE`, `TTS_RATE`, `PERSONALITY_MODE` | Voice and tone (`siri`, `smooth`, `professional`, `chill`) |
| `WAKE_WORD_MODEL`, `WAKE_WORD_THRESHOLD` | Wake word |
| `CLAP_ENERGY_THRESHOLD`, `CLAP_MAX_GAP_MS` | Double-clap tuning |
| `AGENT_MAX_STEPS` | Cap on multi-step plans (default 5) |

Bridge settings (model, effort, extra MCP servers, write mode) are environment variables; see `ui-bridge/README.md`. To cut Claude usage, set `JARVIS_MODEL` to a smaller model and lower `JARVIS_EFFORT`.

---

## Security model

- **Policy file:** `security/policy.json` controls which tools need a spoken confirmation, blocks private/loopback URLs and `file://`, and strips tracking parameters.
- **Claude is held to a stricter bar than your voice.** A model can be steered by text it reads, so when Claude asks Jarvis to act: browser, open and Shortcut actions always need a spoken yes, and `clipboard_read` / `screenshot` are refused.
- **Bridge hardening:**
  - listens on `127.0.0.1` only
  - the Python channel needs a random token (owner-only file at `~/.jarvis/bridge-token`, rotated on every start), and a browser origin can't use it
  - HTTP requests with no allowed origin or referer are refused
  - the agent runs in an empty sandbox folder, and its file-reading tools are confined to it
  - only read-only MCP servers load unless you opt in (`JARVIS_MCP_SERVERS`)
  - navigation, network-body reads and `WebFetch` are off by default, and need write mode plus a confirmation, because a URL can carry data out
  - in read-only mode the built-in write tools are removed outright
- **Privacy:** with the Claude brain on, the text of requests that reach Claude is sent to Anthropic. Speech recognition and the wake word stay on your Mac. With `--local` nothing leaves the machine.
- **Secrets:** `.env`, `memory/actions.json`, `memory/context.json` and `memory/profile.json` are git-ignored.

---

## Project layout

```text
daemon.py, jarvis.py     entry points (always-on / push-to-talk)
core/                    router, agent, planner validation, verifier, executor,
                         brain_local (Ollama), brain_claude + bridge_client + mac_actions
audio/                   listener, wake word, clap trigger, push-to-talk, TTS
tools/                   apps, music, browser, system, Shortcuts, notes, reminders
security/                policy.py + policy.json
services/                AppleScript and Ollama wrappers
memory/                  conversation context and action state
ui-bridge/               Node bridge (Claude Agent SDK) + React/Three.js HUD
scripts/start_all.sh     one-command launcher
tests/                   pytest suite
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest          # Python core, bridge client, action gate, router
ruff check .
```

---

## Credits

`ui-bridge/` is derived from [adewaskar/jarvis](https://github.com/adewaskar/jarvis) (MIT, © 2026 Aditya Dewaskar), with local security changes and a Python-core integration. The license and a `NOTICE.md` are kept in that folder. The boot sound and other audio in `ui-bridge/public/audio/` came with that project; clear the rights before redistributing or monetising.
