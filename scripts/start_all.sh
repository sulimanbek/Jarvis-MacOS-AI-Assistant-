#!/usr/bin/env bash
# Start everything: the bridge, the HUD, and the Python core.
#
#   scripts/start_all.sh               Claude brain + HUD, always-on (wake word / double clap)
#   scripts/start_all.sh --ptt         push-to-talk instead
#   scripts/start_all.sh --writes      let Claude click/type/navigate (each asks first)
#   scripts/start_all.sh --local       HUD + local Ollama brain only; Claude is never contacted
#   scripts/start_all.sh --local --no-hud   headless and fully offline, no Node needed
#
# Ctrl-C stops all of it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

ENTRY="daemon.py"; WRITES=""; LOCAL=0; HUD=1
for arg in "$@"; do
  case "$arg" in
    --ptt)    ENTRY="jarvis.py" ;;
    --writes) WRITES="--writes" ;;
    --local)  LOCAL=1 ;;
    --no-hud) HUD=0 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ "$HUD" = 0 ] && [ "$LOCAL" = 0 ]; then
  echo "--no-hud only makes sense with --local (Claude needs the bridge)." >&2
  exit 2
fi
if [ "$LOCAL" = 1 ] && [ -n "$WRITES" ]; then
  echo "--writes has no effect with --local (Claude is never used)." >&2
  WRITES=""
fi

cd "$ROOT"

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
