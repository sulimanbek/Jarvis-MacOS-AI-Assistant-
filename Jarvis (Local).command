#!/bin/bash
# Double-click me in Finder to start Jarvis.
cd "$(dirname "$0")" || exit 1
clear
echo "  J A R V I S"
echo "  Local brain + HUD (nothing goes to Claude)"
echo "  ------------------------------------------"
echo "  Say 'hey jarvis' or clap twice. Press Ctrl-C to stop."
echo
./scripts/start_all.sh --local
status=$?
echo
if [ "$status" -ne 0 ]; then
  echo "Jarvis stopped with an error (exit $status). Read the lines above for why."
else
  echo "Jarvis stopped."
fi
read -r -n 1 -p "Press any key to close this window. " _
