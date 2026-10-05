#!/usr/bin/env bash
# Start everything: the bridge, the HUD, and the Python core.
#
#   scripts/start_all.sh               Claude brain + HUD, always-on (wake word / double clap)
#   scripts/start_all.sh --ptt         push-to-talk instead
#   scripts/start_all.sh --writes      let Claude click/type/navigate (each asks first)
#   scripts/start_all.sh --local       HUD + local Ollama brain only; Claude is never contacted
#   scripts/start_all.sh --local --no-hud   headless and fully offline, no Node needed
#   scripts/start_all.sh --check       only check that everything is ready; start nothing
#
# Ctrl-C stops all of it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

ENTRY="daemon.py"; WRITES=""; LOCAL=0; HUD=1; CHECK=0
for arg in "$@"; do
  case "$arg" in
    --ptt)    ENTRY="jarvis.py" ;;
    --writes) WRITES="--writes" ;;
    --local)  LOCAL=1 ;;
    --no-hud) HUD=0 ;;
    --check)  CHECK=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ "$HUD" = 0 ] && [ "$LOCAL" = 0 ] && [ "$CHECK" = 0 ]; then
  echo "--no-hud only makes sense with --local (Claude needs the bridge)." >&2
  exit 2
fi
if [ "$LOCAL" = 1 ] && [ -n "$WRITES" ]; then
  echo "--writes has no effect with --local (Claude is never used)." >&2
  WRITES=""
fi

cd "$ROOT"

# ── Preflight ────────────────────────────────────────────────────────────────
# A second Jarvis fights the first over the microphone and the ports, so look
# for one before starting, and only stop it if you say so.
PY_PATTERN='[Pp]ython.* (daemon|jarvis)\.py( |$)'

port_owner() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $1 " (PID " $2 ")"; exit}'
}

preflight() {
  if ! "$PY" -c "import sounddevice, openwakeword, websockets, dotenv" 2>/dev/null; then
    echo "❌ Python packages are missing. Run this once, then try again:" >&2
    echo "     python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    return 1
  fi

  local busy=0 pids p owner owners ans
  pids="$(pgrep -f "$PY_PATTERN" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')"
  if [ -n "$pids" ]; then echo "⚠️  Jarvis is already running (PID $pids)."; busy=1; fi
  if [ "$HUD" = 1 ]; then
    for p in 8787 5173; do
      owner="$(port_owner "$p")"
      if [ -n "$owner" ]; then echo "⚠️  Port $p is in use by $owner."; busy=1; fi
    done
  fi

  if [ "$busy" = 1 ]; then
    if [ "$CHECK" = 0 ] && [ -t 0 ]; then
      read -r -p "Stop them and continue? [y/N] " ans
      if [[ "$ans" =~ ^[Yy]$ ]]; then
        [ -n "$pids" ] && kill $pids 2>/dev/null
        if [ "$HUD" = 1 ]; then
          for p in 8787 5173; do
            owners="$(lsof -t -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null || true)"
            if [ -n "$owners" ]; then kill $owners 2>/dev/null || true; fi
          done
        fi
        sleep 1.5
        return 0
      fi
    fi
    echo "Stop the old one first (Ctrl-C in its window), then run this again." >&2
    return 1
  fi

  if [ "$LOCAL" = 0 ] && ! command -v claude >/dev/null 2>&1; then
    echo "ℹ️  The claude command wasn't found, so Jarvis will use the local model."
  fi
  return 0
}

preflight || exit 1
if [ "$CHECK" = 1 ]; then
  echo "✅ Ready to start. Nothing was launched."
  exit 0
fi

# Which brain the Python core uses. In local mode Claude is never contacted.
if [ "$LOCAL" = 1 ]; then export JARVIS_BRAIN=local; fi

if [ "$HUD" = 0 ]; then
  echo "▶ Headless local mode: no bridge, no HUD, Ollama only."
  exec "$PY" "$ENTRY"
fi

command -v node >/dev/null || { echo "Node.js 20+ is required for the HUD and Claude bridge." >&2; exit 1; }

cd "$ROOT/ui-bridge"
[ -d node_modules ] || { echo "▶ Installing HUD dependencies (first run)…"; npm install --no-audit --no-fund; }

if [ "$LOCAL" = 1 ]; then echo "▶ Starting the HUD (local brain; Claude is not used)…"; else echo "▶ Starting the bridge and HUD…"; fi
# VITE_CORE_MODE=1: the page only displays; the Python core owns mic and voice.
VITE_CORE_MODE=1 node scripts/start.mjs $WRITES &
HUD_PID=$!
cleanup() { kill "$HUD_PID" 2>/dev/null || true; wait "$HUD_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# Wait for the bridge (it answers /health for the HUD's origin).
for _ in $(seq 1 40); do
  if curl -fsS -H "Origin: http://localhost:5173" http://127.0.0.1:8787/health >/dev/null 2>&1; then
    READY=1; break
  fi
  sleep 0.5
done
[ "${READY:-0}" = 1 ] || echo "⚠️  Bridge didn't come up in 20s — the HUD may stay empty; Jarvis itself still works."

open -a "Google Chrome" "http://localhost:5173" 2>/dev/null \
  || echo "Open http://localhost:5173 in Chrome, then click INITIALISE."

cd "$ROOT"
echo "▶ Starting the Python core ($ENTRY)…"
"$PY" "$ENTRY"
