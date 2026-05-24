#!/usr/bin/env python3
"""CareerChat pipeline orchestrator.

Flow per cron tick:
  1. Fetch forum-98 list page 1.
  2. For each thread (newest-bumped first):
     a. If thread_id is already in seen_threads → skip.
     b. Fetch full thread content (主楼 + 回帖).
     c. Call LLM (filter + enrich in one shot).
     d. Write decision row to DB.
     e. If worth=True: push to Telegram via scripts/send_telegram.py.
     f. Polite sleep 2-5s.

Flags:
  --baseline         First run: mark all currently-listed threads as 'baseline'
                     (already seen) without processing. Use once on day 1.
  --dry-run          Don't actually call LLM or send Telegram. Just print plan.
  --max N            Process at most N new threads this tick (safety cap).
  --no-send          Run LLM + write DB, but skip Telegram push.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DB_PATH = ROOT / "career_chat.db"
SCHEMA_PATH = ROOT / "schema.sql"
SEND_SCRIPT = ROOT.parent / "scripts" / "send_telegram.py"

sys.path.insert(0, str(ROOT))
from scrape import fetch_thread_list, fetch_thread_content, polite_sleep  # noqa: E402
from filter_enrich import call_llm  # noqa: E402


def ensure_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def already_seen(conn: sqlite3.Connection, tid: int) -> bool:
    row = conn.execute("SELECT 1 FROM seen_threads WHERE thread_id = ?", (tid,)).fetchone()
    return row is not None


def record_decision(
    conn: sqlite3.Connection,
    thread: dict,
    decision: str,
    reason: str | None = None,
    enriched_md: str | None = None,
    model_name: str | None = None,
    sent: bool = False,
):
    conn.execute(
        """
        INSERT OR REPLACE INTO seen_threads
            (thread_id, title, url, category, author, first_post_date,
             decision, reason, enriched_md, model_name, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread["thread_id"],
            thread["title"],
            thread["url"],
            thread.get("category"),
            thread.get("author"),
            thread.get("first_post_date"),
            decision,
            reason,
            enriched_md,
            model_name,
            datetime.utcnow().isoformat() if sent else None,
        ),
    )
    conn.commit()


def push_telegram(markdown: str) -> bool:
    """Write to temp file, invoke send_telegram.py. Returns True on success."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(markdown)
        tmp = f.name
    try:
        result = subprocess.run(
            ["python3", str(SEND_SCRIPT), tmp],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"  [send_telegram failed] {result.stderr or result.stdout}", file=sys.stderr)
            return False
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def run_baseline():
    """Mark all currently-listed threads as 'baseline' so they're considered seen
    but won't be processed. Use this once before going live so first real tick
    doesn't blast 30 messages."""
    ensure_db()
    threads = fetch_thread_list(page=1)
    conn = sqlite3.connect(DB_PATH)
    try:
        n_new = 0
        for t in threads:
            if already_seen(conn, t["thread_id"]):
                continue
            record_decision(conn, t, decision="baseline", reason="initial baseline mark")
            n_new += 1
        print(f"baseline: marked {n_new} threads as seen (out of {len(threads)} on page 1)")
    finally:
        conn.close()


def run_tick(dry_run: bool = False, max_new: int = 10, send: bool = True):
    ensure_db()
    print(f"=== {datetime.now().isoformat()} fetching list page 1 ===")
    threads = fetch_thread_list(page=1)
    print(f"list page returned {len(threads)} threads")
    conn = sqlite3.connect(DB_PATH)
    try:
        new_threads = [t for t in threads if not already_seen(conn, t["thread_id"])]
        print(f"new (unseen) threads: {len(new_threads)}")
        if len(new_threads) > max_new:
            print(f"capping to first {max_new} for this tick")
            new_threads = new_threads[:max_new]

        for i, t in enumerate(new_threads, 1):
            tid = t["thread_id"]
            print(f"\n[{i}/{len(new_threads)}] thread {tid}: {t['title']}")
            if dry_run:
                print("  (dry-run) would fetch + LLM + maybe send")
                continue
            try:
                content = fetch_thread_content(tid)
                if not content.strip():
                    print("  empty content, skipping")
                    record_decision(conn, t, decision="skip", reason="empty content")
                    continue
                print(f"  fetched {len(content)} chars, calling LLM...")
                parsed, model = call_llm(
                    title=t["title"],
                    url=t["url"],
                    content=content,
                    category=t.get("category"),
                    author=t.get("author"),
                )
                worth = bool(parsed.get("worth"))
                reason = parsed.get("reason") or ""
                md = parsed.get("telegram_markdown")
                print(f"  LLM: worth={worth} ({reason})")
                if worth and md and send:
                    if push_telegram(md):
                        record_decision(conn, t, decision="worth", reason=reason,
                                        enriched_md=md, model_name=model, sent=True)
                        print(f"  ✓ pushed to telegram")
                    else:
                        record_decision(conn, t, decision="worth", reason=f"{reason} [send failed]",
                                        enriched_md=md, model_name=model, sent=False)
                elif worth and md and not send:
                    record_decision(conn, t, decision="worth", reason=reason,
                                    enriched_md=md, model_name=model, sent=False)
                    print(f"  (--no-send) skipped telegram push")
                else:
                    record_decision(conn, t, decision="skip", reason=reason, model_name=model)
            except Exception as e:
                print(f"  ERROR: {e}")
                traceback.print_exc()
                record_decision(conn, t, decision="error", reason=str(e)[:500])
            finally:
                polite_sleep()
        print(f"\n=== tick done ===")
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", action="store_true",
                   help="Mark all current page-1 threads as seen, don't process")
    p.add_argument("--dry-run", action="store_true",
                   help="List what would be done, no LLM calls or sends")
    p.add_argument("--no-send", action="store_true",
                   help="Run LLM + write DB, but skip Telegram push (useful for testing)")
    p.add_argument("--max", type=int, default=10,
                   help="Cap new threads per tick (default 10)")
    args = p.parse_args()

    if args.baseline:
        run_baseline()
    else:
        run_tick(dry_run=args.dry_run, max_new=args.max, send=not args.no_send)


if __name__ == "__main__":
    main()
