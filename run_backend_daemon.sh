#!/bin/bash
# Run backend in background. Safe to close terminal.
cd "$(dirname "$0")/backend"
source venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
echo "Backend started in background. Log: backend.log"
echo "To stop: pkill -f 'uvicorn main:app'"
