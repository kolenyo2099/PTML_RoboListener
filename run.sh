#!/usr/bin/env bash
set -Eeuo pipefail

# Start RoboListener locally. Override ports with BACKEND_PORT / FRONTEND_PORT.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_PID=""
FRONTEND_PID=""

die() { printf 'RoboListener: %s\n' "$*" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || die "Python 3 is required. Install it from https://www.python.org/downloads/"
command -v npm >/dev/null 2>&1 || die "Node.js and npm are required. Install the current LTS release from https://nodejs.org/"
command -v curl >/dev/null 2>&1 || die "curl is required to check when RoboListener is ready."
[[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] && (( BACKEND_PORT > 0 && BACKEND_PORT < 65536 )) || die "BACKEND_PORT must be between 1 and 65535."
[[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] && (( FRONTEND_PORT > 0 && FRONTEND_PORT < 65536 )) || die "FRONTEND_PORT must be between 1 and 65535."
(( BACKEND_PORT != FRONTEND_PORT )) || die "Backend and frontend ports must be different."

cd "$ROOT_DIR"
if [[ ! -x .venv/bin/uvicorn || ! -x frontend/node_modules/.bin/vite ]]; then
  echo "First-time setup is needed; installing project dependencies..."
  "$ROOT_DIR/setup.sh"
fi

port_busy() {
  # lsof ships with macOS; the Python fallback also works on Linux.
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(0)
else:
    sys.exit(1)
finally:
    s.close()
PY
  fi
}

port_busy "$BACKEND_PORT" && die "Port $BACKEND_PORT is already in use. Stop the other app or run with BACKEND_PORT=<free port>."
port_busy "$FRONTEND_PORT" && die "Port $FRONTEND_PORT is already in use. Stop the other app or run with FRONTEND_PORT=<free port>."

cleanup() {
  trap - EXIT INT TERM
  [[ -z "$FRONTEND_PID" ]] || kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -z "$BACKEND_PID" ]] || kill "$BACKEND_PID" 2>/dev/null || true
  [[ -z "$FRONTEND_PID" ]] || wait "$FRONTEND_PID" 2>/dev/null || true
  [[ -z "$BACKEND_PID" ]] || wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$ROOT_DIR/.venv/bin/uvicorn" app.main:app --app-dir "$ROOT_DIR/backend" --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!
(cd "$ROOT_DIR/frontend" && export BACKEND_PORT && exec ./node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort) &
FRONTEND_PID=$!

APP_URL="http://127.0.0.1:${FRONTEND_PORT}"
echo "RoboListener is starting..."
ready=0
for _ in $(seq 1 60); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    die "The backend stopped during startup. Check the error above."
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    die "The frontend stopped during startup. Check the error above."
  fi
  if curl -fsS "$APP_URL" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:${BACKEND_PORT}/openapi.json" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
(( ready == 1 )) || die "RoboListener did not become ready within 60 seconds. Check the errors above."

echo "RoboListener is ready: $APP_URL"
echo "Backend: http://127.0.0.1:${BACKEND_PORT}"
echo "Keep this window open while using RoboListener. Press Ctrl+C to stop it."
if [[ "$(uname -s)" == Darwin ]]; then
  open "$APP_URL" >/dev/null 2>&1 || echo "Open $APP_URL in your browser."
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$APP_URL" >/dev/null 2>&1 || true
fi
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 2
done
die "A service stopped. RoboListener is shutting down; check the messages above."
