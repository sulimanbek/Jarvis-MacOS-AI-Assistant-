#!/usr/bin/env bash
# Start Jarvis automatically when you log in to your Mac.
#
#   scripts/autostart.sh install            start at login (Claude brain + HUD)
#   scripts/autostart.sh install --local    start at login (local brain + HUD)
#   scripts/autostart.sh uninstall          stop starting at login
#   scripts/autostart.sh status             show what is set up
#   scripts/autostart.sh start              start it now through the same agent
#
# How it works: a macOS login agent waits 15 seconds (so the desktop and network
# are up), then opens Terminal running Jarvis.command. It goes through Terminal
# on purpose: your microphone, Calendar and Automation permissions belong to
# Terminal, and a background process started by macOS itself usually cannot get
# them. You also see Jarvis running and can stop it with Ctrl-C.
#
# `install` only writes the agent. It starts at your next login; use `start` to
# run it right now.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${JARVIS_LABEL:-com.jarvis.assistant}"
AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST="$AGENTS_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"
LOG="$HOME/Library/Logs/jarvis-autostart.log"

action="${1:-status}"
[ "$#" -gt 0 ] && shift

variant="Jarvis.command"
for arg in "$@"; do
  case "$arg" in
    --local) variant="Jarvis (Local).command" ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

loaded() { launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; }

case "$action" in
  install)
    target="$ROOT/$variant"
    [ -f "$target" ] || { echo "Can't find $target" >&2; exit 1; }
    mkdir -p "$AGENTS_DIR" "$(dirname "$LOG")"
    # Written with plistlib so a path with spaces or brackets can't break the XML.
    python3 - "$PLIST" "$LABEL" "$target" "$LOG" <<'PY'
import plistlib, sys
plist_path, label, target, log = sys.argv[1:5]
data = {
    "Label": label,
    # $0 is the launcher path, passed as an argument so it needs no quoting.
    "ProgramArguments": ["/bin/bash", "-c", 'sleep 15; exec /usr/bin/open -a Terminal "$0"', target],
    "RunAtLoad": True,
    "LimitLoadToSessionType": "Aqua",
    "StandardOutPath": log,
    "StandardErrorPath": log,
}
with open(plist_path, "wb") as f:
    plistlib.dump(data, f)
PY
    plutil -lint "$PLIST" >/dev/null
    echo "✅ Jarvis will start at your next login ($variant)."
    echo "   Start it now:   scripts/autostart.sh start"
    echo "   Turn it off:    scripts/autostart.sh uninstall"
    echo "   macOS may show a 'background item added' notice; it can be managed in"
    echo "   System Settings > General > Login Items & Extensions."
    ;;

  uninstall)
    if loaded; then launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true; fi
    if [ -f "$PLIST" ]; then rm "$PLIST"; echo "✅ Removed. Jarvis won't start at login."; else echo "Nothing to remove."; fi
    ;;

  start)
    [ -f "$PLIST" ] || { echo "Not installed. Run: scripts/autostart.sh install" >&2; exit 1; }
    if loaded; then launchctl kickstart -k "$DOMAIN/$LABEL"; else launchctl bootstrap "$DOMAIN" "$PLIST"; fi
    echo "Started. Terminal should open in about 15 seconds."
    ;;

  status)
    if [ -f "$PLIST" ]; then
      shown="$(plutil -extract ProgramArguments.3 raw "$PLIST" 2>/dev/null || echo "?")"
      echo "Installed:  yes ($(basename "$shown"))"
    else
      echo "Installed:  no"
    fi
    if loaded; then echo "Loaded now: yes"; else echo "Loaded now: no (it loads at login)"; fi
    ;;

  *)
    sed -n '2,12p' "$0"; exit 2 ;;
esac
