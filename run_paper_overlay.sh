#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  python3 paper_overlay.py "$@"
  exit $?
fi

if [[ -z "${DISPLAY:-}" ]]; then
  echo "No DISPLAY detected. Start an X11 session on Cinnamon/Linux Mint and run the launcher again." >&2
  exit 1
fi

export QT_QPA_PLATFORM=xcb
python3 paper_overlay.py "$@" --preset parchment --opacity 0.9 --grain 0.25
