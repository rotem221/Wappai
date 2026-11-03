#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then
  cp deploy/companion.env.example .env
  chmod 600 .env
  .venv/bin/python -c 'from pathlib import Path; import secrets; p=Path(".env"); p.write_text(p.read_text().replace("GENERATE_YOUR_OWN_TOKEN",secrets.token_hex(32)))'
fi
printf '%s
' 'Edit server/.env, sign in to your chosen brain provider, then run:' '.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8770 --no-access-log'
