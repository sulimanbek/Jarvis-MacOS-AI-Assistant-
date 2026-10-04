#!/usr/bin/env bash
# Start everything: the bridge (Claude), the HUD, and the Python core.
#
#   scripts/start_all.sh            always-on (wake word / double clap)
#   scripts/start_all.sh --ptt      push-to-talk instead
#   scripts/start_all.sh --writes   let Claude click/type/navigate (each asks first)
#   scripts/start_all.sh --local    Ollama only, no bridge, fully offline
#
# Ctrl-C stops all of it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

ENTRY="daemon.py"; WRITES=""; LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --ptt)    ENTRY="jarvis.py" ;;
    --writes) WRITES="--writes" ;;
    --local)  LOCAL=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

cd "$ROOT"

if [ "$LOCAL" = 1 ]; then
  echo "▶ Local mode: no bridge, no HUD, Ollama only."
  JARVIS_BRAIN=local exec "$PY" "$ENTRY"
fi

command -v node >/dev/null || { echo "Node.js 20+ is required for the HUD and Claude bridge." >&2; exit 1; }

cd "$ROOT/ui-bridge"
[ -d node_modules ] || { echo "▶ Installing HUD dependencies (first run)…"; npm install --no-audit --no-fund; }

echo "▶ Starting the bridge and HUD…"
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
[ "${READY:-0}" = 1 ] || echo "⚠️  Bridge didn't come up in 20s — the core will fall back to the local model."

open -a "Google Chrome" "http://localhost:5173" 2>/dev/null \
  || echo "Open http://localhost:5173 in Chrome, then click INITIALISE."

cd "$ROOT"
echo "▶ Starting the Python core ($ENTRY)…"
"$PY" "$ENTRY"
