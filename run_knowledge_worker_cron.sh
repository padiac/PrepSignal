#!/bin/bash
# Cron wrapper: run knowledge worker, log to file
cd "$(dirname "$0")"
LOG="$PWD/knowledge_worker.log"
exec >> "$LOG" 2>&1
echo "=== $(date -Iseconds) ==="
./run_knowledge_worker.sh --limit 20   # 每4小时跑一次，处理20个 thread
echo ""
