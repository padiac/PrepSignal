#!/usr/bin/env python3
"""Send a markdown file to Telegram via Bot API.

Replaces the old openclaw-based send_chunks.py. No dependency on openclaw.

Usage: python3 send_telegram.py <file>

Config:
- TELEGRAM_BOT_TOKEN env var (or falls back to reading openclaw.json)
- TELEGRAM_CHAT_ID env var (or defaults to known target)

Chunks long messages on paragraph/line boundaries with [n/N] header,
because Telegram limits messages to 4096 chars (we use 3500 for safety).
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_LEN = 3500
DEFAULT_CHAT_ID = "8753167154"
OPENCLAW_CONFIG_FALLBACK = Path.home() / ".openclaw" / "openclaw.json"
RETRY_DELAYS = (2, 5, 15)  # seconds between retries on transient failure


def get_bot_token() -> str:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if tok:
        return tok.strip()
    if OPENCLAW_CONFIG_FALLBACK.exists():
        try:
            cfg = json.loads(OPENCLAW_CONFIG_FALLBACK.read_text(encoding="utf-8"))
            # openclaw stores it under various paths — search recursively
            stack = [cfg]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if "botToken" in node and isinstance(node["botToken"], str):
                        return node["botToken"].strip()
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
        except Exception:
            pass
    raise SystemExit(
        "No Telegram bot token. Set TELEGRAM_BOT_TOKEN env var, "
        "or ensure ~/.openclaw/openclaw.json contains botToken."
    )


def split_balanced(text: str, max_len: int = MAX_LEN) -> list[str]:
    text = text.strip()
    if len(text) <= max_len:
        return [text]
    target_parts = math.ceil(len(text) / max_len)
    target_size = math.ceil(len(text) / target_parts)
    parts: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        window = min(max_len, target_size)
        cut = remaining.rfind("\n\n", 0, window)
        if cut == -1 or cut < int(window * 0.6):
            cut = remaining.rfind("\n", 0, window)
        if cut == -1 or cut < int(window * 0.6):
            cut = window
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


def send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode("utf-8")
    last_err: Exception | None = None
    for attempt, delay in enumerate([0, *RETRY_DELAYS]):
        if delay:
            time.sleep(delay)
        try:
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                parsed = json.loads(body)
                if not parsed.get("ok"):
                    raise RuntimeError(f"Telegram API error: {body}")
                return
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            last_err = e
            print(
                f"  send attempt {attempt + 1} failed: {e}",
                file=sys.stderr,
            )
    raise SystemExit(f"Failed to send Telegram message after retries: {last_err}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: send_telegram.py <file>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    chunks = split_balanced(text)
    total = len(chunks)
    token = get_bot_token()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", DEFAULT_CHAT_ID).strip()
    for i, chunk in enumerate(chunks, 1):
        payload = f"【{i}/{total}】\n{chunk}" if total > 1 else chunk
        send_message(token, chat_id, payload)
        if i < total:
            time.sleep(0.5)  # avoid Telegram rate limit (30 msg/sec global)
    print(f"sent {total} chunk(s) to chat {chat_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
