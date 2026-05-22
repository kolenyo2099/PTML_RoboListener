#!/usr/bin/env bash
set -euo pipefail

# Starts the local RadioWatch backend and frontend together.
# The script assumes setup.sh has already created .venv and installed npm
# packages. If not, it runs setup.sh first so non-technical users have one
# command that works from a fresh checkout.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

cd "$ROOT_DIR"

if [ ! -d ".venv" ] || [ ! -d "frontend/node_modules" ]; then
  ./setup.sh
fi

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

source "$ROOT_DIR/.venv/bin/activate"

uvicorn app.main:app \
  --app-dir backend \
  --host 127.0.0.1 \
  --port "$BACKEND_PORT" &
BACKEND_PID=$!

(cd frontend && npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

echo "RadioWatch is starting."
echo "Backend:  http://127.0.0.1:${BACKEND_PORT}"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "Press Ctrl+C to stop both servers."

wait "$BACKEND_PID" "$FRONTEND_PID"

