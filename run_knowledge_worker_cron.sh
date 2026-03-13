#!/bin/bash
# Cron wrapper: run knowledge worker, log to file
# Cron has minimal PATH - set agent path explicitly
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME:-/home/padiac}/.local/bin:$PATH"
export CURSOR_AGENT_PATH="${HOME:-/home/padiac}/.local/bin/agent"
cd "$(dirname "$0")"
LOG="$PWD/knowledge_worker.log"
exec >> "$LOG" 2>&1
echo "=== $(date -Iseconds) ==="
./run_knowledge_worker.sh --all
echo ""
