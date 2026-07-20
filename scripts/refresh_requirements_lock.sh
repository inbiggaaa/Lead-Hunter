#!/usr/bin/env bash
# Refresh requirements.lock from requirements.txt ranges (Python 3.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker run --rm -v "$ROOT:/app" -w /app python:3.11-slim bash -c '
  set -euo pipefail
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
  pip freeze | sort > requirements.lock
  echo "Wrote requirements.lock ($(wc -l < requirements.lock) packages)"
'
