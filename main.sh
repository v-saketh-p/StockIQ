#!/bin/bash
# StockIQ — start / stop helper
# Usage:
#   ./main.sh          start everything
#   ./main.sh stop     kill backend, frontend, and ollama

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Colours ──────────────────────────────────────────────────────────────────
BOLD="\033[1m"; RESET="\033[0m"
GREEN="\033[32m"; BLUE="\033[34m"; YELLOW="\033[33m"; RED="\033[31m"

log()  { echo -e "${BOLD}${BLUE}[StockIQ]${RESET} $*"; }
ok()   { echo -e "${BOLD}${GREEN}  ✓${RESET} $*"; }
warn() { echo -e "${BOLD}${YELLOW}  !${RESET} $*"; }
err()  { echo -e "${BOLD}${RED}  ✗${RESET} $*"; }

# ── Stop ─────────────────────────────────────────────────────────────────────
if [[ "$1" == "stop" ]]; then
  log "Stopping all StockIQ processes…"
  pkill -f "uvicorn main:app" 2>/dev/null && ok "Backend stopped"  || warn "Backend was not running"
  pkill -f "next dev"         2>/dev/null && ok "Frontend stopped" || warn "Frontend was not running"
  pkill -f "ollama serve"     2>/dev/null && ok "Ollama stopped"   || warn "Ollama was not running"
  exit 0
fi

# ── Start ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}  ╔══════════════════════════╗"
echo -e "  ║       StockIQ  v1.0      ║"
echo -e "  ╚══════════════════════════╝${RESET}"
echo ""

# 1. Ollama
if pgrep -f "ollama serve" >/dev/null; then
  ok "Ollama already running"
else
  log "Starting Ollama…"
  ollama serve &>/tmp/stockiq-ollama.log &
  sleep 1
  if pgrep -f "ollama serve" >/dev/null; then ok "Ollama started"
  else err "Ollama failed to start — check /tmp/stockiq-ollama.log"; fi
fi

# 2. Backend
if lsof -i:8000 >/dev/null 2>&1; then
  ok "Backend already running on :8000"
else
  log "Starting backend…"
  cd "$ROOT/backend"
  .venv/bin/uvicorn main:app --port 8000 --reload &>/tmp/stockiq-backend.log &
  # Wait up to 8 s for port 8000
  for i in {1..8}; do
    sleep 1
    lsof -i:8000 >/dev/null 2>&1 && break
  done
  if lsof -i:8000 >/dev/null 2>&1; then ok "Backend ready → http://localhost:8000"
  else err "Backend failed — check /tmp/stockiq-backend.log"; fi
fi

# 3. Frontend
if lsof -i:3000 >/dev/null 2>&1; then
  ok "Frontend already running on :3000"
else
  log "Starting frontend…"
  cd "$ROOT/frontend"
  npm run dev &>/tmp/stockiq-frontend.log &
  # Wait up to 20 s for port 3000
  for i in {1..20}; do
    sleep 1
    lsof -i:3000 >/dev/null 2>&1 && break
  done
  if lsof -i:3000 >/dev/null 2>&1; then ok "Frontend ready → http://localhost:3000"
  else err "Frontend failed — check /tmp/stockiq-frontend.log"; fi
fi

# 4. Open browser
echo ""
log "Opening StockIQ in your browser…"
open http://localhost:3000

echo ""
echo -e "${BOLD}${GREEN}  All systems go!${RESET}  →  http://localhost:3000"
echo -e "  Logs: /tmp/stockiq-{backend,frontend,ollama}.log"
echo -e "  Stop: ${BOLD}./main.sh stop${RESET}"
echo ""
