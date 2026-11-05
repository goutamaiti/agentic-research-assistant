#!/usr/bin/env bash
# Agentic Research Assistant - one-command launcher for macOS/Linux.
# First run installs everything and asks for an API key; later runs start at once.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8000}"

PY=""
for candidate in python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || { echo "Python 3.12 or newer is required: https://www.python.org/downloads/"; exit 1; }

[ -x backend/.venv/bin/python ] || { echo "[1/4] Creating the Python environment..."; "$PY" -m venv backend/.venv; }
if ! cmp -s backend/requirements.txt backend/.venv/installed-requirements.txt; then
  echo "[2/4] Installing Python packages (first run takes several minutes)..."
  backend/.venv/bin/python -m pip install --upgrade pip >/dev/null
  backend/.venv/bin/python -m pip install -r backend/requirements.txt
  cp backend/requirements.txt backend/.venv/installed-requirements.txt
fi

if command -v npm >/dev/null 2>&1; then
  echo "[3/4] Building the web interface..."
  (cd frontend && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build >/dev/null)
elif [ ! -f frontend/dist/index.html ]; then
  echo "Node.js is needed once to build the web interface: https://nodejs.org/"; exit 1
fi

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "[4/4] Paste your Google Gemini API key (or an OpenRouter sk-or- key), or press Enter to skip:"
  read -r -s APIKEY || true
  if [ -n "${APIKEY:-}" ]; then
    APIKEY="$APIKEY" "$PY" - <<'PYEOF'
import os, pathlib, re
p = pathlib.Path("backend/.env")
p.write_text(re.sub(r"(?m)^GEMINI_API_KEY=.*$", "GEMINI_API_KEY=" + os.environ["APIKEY"], p.read_text()))
PYEOF
  fi
  unset APIKEY
fi

echo "Starting at http://127.0.0.1:${PORT} (Ctrl+C to stop)"
( sleep 8; command -v xdg-open >/dev/null && xdg-open "http://127.0.0.1:${PORT}" || open "http://127.0.0.1:${PORT}" ) >/dev/null 2>&1 &
cd backend && exec .venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${PORT}"
