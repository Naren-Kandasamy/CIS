#!/bin/bash
echo "Starting PS-1 Backend (Port 8000)..."
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting PS-1 Frontend (Port 5173)..."
cd client && npm run dev &
FRONTEND_PID=$!

echo "Both servers running. Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
