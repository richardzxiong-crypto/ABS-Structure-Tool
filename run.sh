#!/usr/bin/env bash
# One-click launcher: sets up (or refreshes) dependencies, starts the API and
# UI, and opens the app in your browser. Safe to re-run after every git pull.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1;34m» %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*"; read -rp "Press Enter to close..."; exit 1; }

# ---- prerequisites -----------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "Python 3 is not installed. Get it from https://www.python.org/downloads/ (3.11+) and re-run."
command -v node >/dev/null 2>&1 || die "Node.js is not installed. Get it from https://nodejs.org (18+) and re-run."

if ! command -v uv >/dev/null 2>&1; then
  # uv installs to ~/.local/bin; pick it up if a previous run installed it
  export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (fast Python package manager, one-time)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || die "Could not install uv."
  export PATH="$HOME/.local/bin:$PATH"
fi

# ---- setup / refresh (fast no-op when nothing changed) -----------------------
say "Syncing backend dependencies..."
(cd backend && uv venv .venv --allow-existing -q && uv pip install -q -e ".[dev]") || die "Backend setup failed."

say "Syncing frontend dependencies..."
(cd frontend && npm install --silent --no-audit --no-fund) || die "Frontend setup failed (npm install)."

# ---- launch ------------------------------------------------------------------
cleanup() {
  say "Shutting down..."
  kill "${API_PID:-}" "${UI_PID:-}" 2>/dev/null || true
  # catch the whole tree (npx -> sh -> node), portable to macOS + Linux
  pkill -f "uvicorn app.main:app --port 8000" 2>/dev/null || true
  pkill -f "vite --port 5173" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

say "Starting API on http://localhost:8000 ..."
(cd backend && exec .venv/bin/python -m uvicorn app.main:app --port 8000) &
API_PID=$!

say "Starting UI on http://localhost:5173 ..."
(cd frontend && exec npx vite --port 5173) &
UI_PID=$!

# wait for the UI to come up, then open the browser
for _ in $(seq 1 30); do
  sleep 1
  if curl -s -o /dev/null "http://localhost:5173"; then break; fi
done
say "Opening http://localhost:5173 in your browser..."
if command -v open >/dev/null 2>&1; then open "http://localhost:5173"        # macOS
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:5173"  # Linux
fi

say "App is running. Keep this window open; press Ctrl+C to stop."
wait
