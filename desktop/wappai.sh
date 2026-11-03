#!/bin/sh
cd "$(dirname "$0")/.." || exit 1
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,11))' 2>/dev/null; then
    exec "$candidate" desktop/wappai_hub.py "$@"
  fi
done
printf '%s\n' 'Wappai needs Python 3.11 or newer: https://www.python.org/downloads/'
exit 1
