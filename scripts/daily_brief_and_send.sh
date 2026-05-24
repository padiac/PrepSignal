#!/usr/bin/env bash
# Daily brief: generate today's PrepSignal brief via Claude Code, then push to Telegram.
# Independent of openclaw — uses Telegram Bot API directly.
#
# Run by cron: 30 8 * * * (8:30 AM America/Los_Angeles)
set -euo pipefail

SCRIPTS_DIR="/home/padiac/PrepSignal/scripts"
REPORT_DIR="/home/padiac/PrepSignal/reports/daily"
BRIEF_SCRIPT="$SCRIPTS_DIR/agent_brief.py"
SEND_SCRIPT="$SCRIPTS_DIR/send_telegram.py"
LOG_FILE="$REPORT_DIR/cron.log"

# Cron has minimal PATH — include Windows npm for the claude CLI
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME:-/home/padiac}/.local/bin:/mnt/c/Users/pppad/AppData/Roaming/npm:$PATH"

TODAY=$(TZ=America/Los_Angeles date +%F)
LATEST="$REPORT_DIR/latest.md"
DAILY="$REPORT_DIR/${TODAY}.md"

mkdir -p "$REPORT_DIR"
echo "=== $(date -Iseconds) generating brief for $TODAY ===" >> "$LOG_FILE"

# Generate
/usr/bin/python3 "$BRIEF_SCRIPT" "$TODAY" > "$LATEST" 2>> "$LOG_FILE"
cp "$LATEST" "$DAILY"

# Send
/usr/bin/python3 "$SEND_SCRIPT" "$LATEST" >> "$LOG_FILE" 2>&1

echo "=== done ===" >> "$LOG_FILE"
