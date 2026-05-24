#!/bin/bash
# Cron wrapper: run knowledge worker, log to file
# Cron has minimal PATH - include Windows npm path for claude CLI
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME:-/home/padiac}/.local/bin:/mnt/c/Users/pppad/AppData/Roaming/npm:$PATH"
export CURSOR_AGENT_PATH="${HOME:-/home/padiac}/.local/bin/agent"
cd "$(dirname "$0")"
LOG="$PWD/knowledge_worker.log"
exec >> "$LOG" 2>&1
echo "=== $(date -Iseconds) ==="
./run_knowledge_worker.sh --all
echo ""
