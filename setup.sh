#!/usr/bin/env bash
set -euo pipefail

# This script prepares the project in the same way on every machine.
# It uses uv for Python, npm for the browser app, and initializes git
# if the folder is not already under version control.

if [ ! -d ".git" ]; then
  git init
fi

if [ ! -d ".venv" ]; then
  uv venv
fi

uv pip install -r requirements.txt

if [ -d "frontend" ]; then
  (cd frontend && npm install)
fi

echo "Setup complete."
echo "Backend: source .venv/bin/activate && uvicorn app.main:app --reload --app-dir backend"
echo "Frontend: cd frontend && npm run dev"

