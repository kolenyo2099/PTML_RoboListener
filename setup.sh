#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required. Install it from https://www.python.org/downloads/" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Node.js and npm are required. Install the current LTS release from https://nodejs.org/" >&2; exit 1; }
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required. Install it from https://www.python.org/downloads/")
PY

if [[ ! -d .venv ]]; then
  python3 -m venv .venv || { echo "Could not create .venv. Ensure your Python installation includes venv support." >&2; exit 1; }
fi
"$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt"

if [[ -f frontend/package-lock.json ]]; then
  (cd frontend && npm ci)
else
  (cd frontend && npm install)
fi

echo "Setup complete. Run ./run.sh (or double-click Start RoboListener.command)."
