#!/usr/bin/env bash
# ==============================================================================
# Goldman Sachs Hackathon - Unified Application Startup Script
# Starts both FastAPI Backend (port 8000) and React Vite Frontend (port 5173).
# Usage:
#   ./start.sh          -> Starts in Development mode (hot-reloading enabled)
#   ./start.sh --prod   -> Builds frontend and serves unified via FastAPI (port 8000)
# ==============================================================================

set -e

# Resolve script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  GS Hackathon - Alerting & Management Platform   "
echo "=================================================="

# 1. Environment file (.env) setup
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[SETUP] No .env file found. Creating .env from .env.example..."
        cp .env.example .env
    else
        echo "[WARNING] Neither .env nor .env.example found. Continuing with default settings."
    fi
fi

# 2. Virtual environment (.venv) check
if [ ! -d ".venv" ]; then
    echo "[SETUP] Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
fi

# Determine python and pip binaries
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
PIP_BIN="$SCRIPT_DIR/.venv/bin/pip"
UVICORN_BIN="$SCRIPT_DIR/.venv/bin/uvicorn"

if [ ! -f "$PYTHON_BIN" ]; then
    # Fallback for Windows git-bash
    PYTHON_BIN="$SCRIPT_DIR/.venv/Scripts/python.exe"
    PIP_BIN="$SCRIPT_DIR/.venv/Scripts/pip.exe"
    UVICORN_BIN="$SCRIPT_DIR/.venv/Scripts/uvicorn.exe"
fi

# Check requirements
if [ -f "requirements.txt" ]; then
    if [ ! -f "$UVICORN_BIN" ]; then
        echo "[SETUP] Installing Python dependencies from requirements.txt..."
        "$PIP_BIN" install -r requirements.txt
    fi
fi

# 3. Node & Frontend dependencies check
if [ -d "frontend" ]; then
    if [ ! -d "frontend/node_modules" ]; then
        echo "[SETUP] Installing frontend npm dependencies..."
        npm --prefix frontend install
    fi
fi

# 4. Mode determination (--prod vs development)
MODE="dev"
if [[ "$1" == "--prod" || "$1" == "--build" || "$PROD" == "1" ]]; then
    MODE="prod"
fi

if [ "$MODE" == "prod" ]; then
    echo "[BUILD] Building production frontend bundle..."
    npm --prefix frontend run build

    echo ""
    echo "--------------------------------------------------"
    echo "  Production Server Starting                      "
    echo "  Application URL: http://localhost:8000          "
    echo "  API Docs:        http://localhost:8000/docs     "
    echo "--------------------------------------------------"
    echo "Press Ctrl+C to stop."
    echo ""

    exec "$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port 8000
fi

# Development Mode: Run both backend and frontend concurrently
echo "[MODE] Starting in Development Mode with Hot-Reloading..."

# Trap signals to ensure background processes are killed on exit
cleanup() {
    echo ""
    echo "[SHUTDOWN] Stopping all services..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Start Backend API
echo "[BACKEND] Starting FastAPI server on http://localhost:8000..."
"$PYTHON_BIN" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 &

# Start Frontend Vite Dev Server
echo "[FRONTEND] Starting Vite dev server on http://localhost:5173..."
npm --prefix frontend run dev &

echo ""
echo "--------------------------------------------------"
echo "  All services are running!                       "
echo "  Frontend UI:  http://localhost:5173             "
echo "  Backend API:  http://localhost:8000             "
echo "  API Docs:     http://localhost:8000/docs        "
echo "--------------------------------------------------"
echo "Press Ctrl+C to terminate both servers."
echo ""

# Wait for both processes
wait
