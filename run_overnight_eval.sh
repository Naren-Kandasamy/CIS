#!/bin/bash
# run_overnight_eval.sh
# This script spins up the local backend, runs the 1,000-query protocol, and safely tears everything down.

echo "=========================================================="
echo "🌙 PS-1 Overnight Confidence Calibration Protocol Initiated"
echo "=========================================================="

# 1. Start the backend in the background
echo "[1/4] Booting local FastAPI backend..."
export PYTHONPATH="$(pwd)"
python3 -m uvicorn backend.main:app --port 8000 &
BACKEND_PID=$!

# 2. Wait for the backend to be healthy
echo "[2/4] Waiting for backend to initialize (10 seconds)..."
sleep 10

# 3. Execute the 1,000-query generation script
echo "[3/4] Launching the 2-hour 1,000-query drip feed..."
python3 data/scripts/generate_1000_synthetic_queries.py

# 4. Cleanup
echo "[4/4] Evaluation complete! Tearing down backend..."
kill $BACKEND_PID

echo "=========================================================="
echo "✅ Process finished. You can find your evaluation packet at:"
echo "   data/scripts/blind_evaluation_1000.csv"
echo "=========================================================="
