#!/bin/bash
# ==========================================
# PS-1 Local Development & Evaluation Script
# ==========================================

# 1. Source the production environment variables
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "Starting PS-1 Backend (Port 8000)..."
# Start the FastAPI backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting PS-1 Frontend (Port 5173)..."
cd client && npm run dev &
FRONTEND_PID=$!

echo "=========================================="
echo "Both servers running."
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo "Press Ctrl+C to stop."
echo "=========================================="

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
