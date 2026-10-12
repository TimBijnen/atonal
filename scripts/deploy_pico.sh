#!/usr/bin/env bash
set -eu

PICO_PORT="${1:-${PICO_PORT:-/dev/ttyACM0}}"
MPREMOTE="${MPREMOTE:-mpremote}"

FILES=(
  main.py
  config.py
  display.py
  hw.py
  logic.py
  menu.py
  sequencer.py
  toneclock.py
)

if ! command -v "$MPREMOTE" >/dev/null 2>&1; then
  echo "mpremote not found. Install it with:"
  echo "  python3 -m pip install mpremote"
  exit 1
fi

for f in "${FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing file: $f" >&2
    exit 1
  fi
done

echo "Deploying Pico firmware to $PICO_PORT"
for f in "${FILES[@]}"; do
  echo "  -> $f"
  "$MPREMOTE" connect "$PICO_PORT" fs cp "$f" ":/$f"
done

echo "Deployment complete."
