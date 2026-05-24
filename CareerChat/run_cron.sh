#!/usr/bin/env bash
# CareerChat: scrape 一亩三分地 forum-98 (职场达人), filter+enrich via Claude Code,
# push valuable threads to Telegram. Runs every 30 minutes via cron.
set -euo pipefail

DIR="/home/padiac/PrepSignal/CareerChat"
VENV="/home/padiac/PrepSignal/backend/venv/bin/python3"
LOG_FILE="$DIR/cron.log"

# Cron's minimal PATH — include Windows npm for claude CLI
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME:-/home/padiac}/.local/bin:/mnt/c/Users/pppad/AppData/Roaming/npm:$PATH"

mkdir -p "$DIR"
echo "=== $(date -Iseconds) tick ===" >> "$LOG_FILE"
"$VENV" "$DIR/pipeline.py" "$@" >> "$LOG_FILE" 2>&1
echo "" >> "$LOG_FILE"
