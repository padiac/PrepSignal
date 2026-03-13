#!/usr/bin/env python3
"""
Knowledge worker: reads raw_posts, uses LLM to interpret, writes to interpreted_posts.
Default: Cursor Agent CLI.
Run: python knowledge_worker.py [--limit N] [--dry-run]
     python knowledge_worker.py --api [--limit N]    # Use OpenAI/Anthropic instead
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def _parse_llm_json(text):
    """Parse JSON from LLM output, with fallbacks for common malformations."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        for p in parts[1:]:
            p = p.lstrip("json\n")
            if p.strip().startswith("{"):
                text = p.strip()
                break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fix trailing commas before ] or }
    fixed = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Extract first complete {...} with bracket matching
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    # Truncate at last } in case of trailing garbage
    last_brace = text.rfind("}")
    if last_brace > 0:
        try:
            return json.loads(text[: last_brace + 1])
        except json.JSONDecodeError:
            pass
    # Repair truncated JSON (LLM output cut off mid-string, e.g. in detailed_summary)
    if text.strip().startswith("{") and '"detailed_summary"' in text:
        repaired = text.rstrip()
        if not repaired.endswith("}"):
            if repaired[-1] not in ('"', "}", "]"):
                repaired += '"'
            if '"confidence"' not in repaired[-300:]:
                repaired += ', "confidence": 0.5'
            suffixes = ["}", "]}", "}]}", "]}", "}", "]}", "}", "]}", "}", "]"]
            for suf in suffixes:
                try:
                    return json.loads(repaired + suf)
                except json.JSONDecodeError:
                    pass
    raise ValueError(f"Invalid JSON from LLM (first 300 chars): {repr(text[:300])}")

DB_PATH = Path(__file__).parent / "raw_posts.db"

PROMPT = """你正在破译一亩三分地面的面经帖（thread，含楼内所有回复），输出结构化知识。目标：越详细越好，不压缩。

以下是一个 thread 的完整内容，可能包含主帖 + 楼内多条回复，请作为整体破译：

## Thread 完整内容
---
{content}
---

## Scraper metadata（仅供参考）
company={company}, job_title={job_title}, thread_title={thread_title}

## 输出要求

1. **公司/方向/轮次**
   - company: 公司名
   - direction: 岗位方向，如 MLE, SDE Backend, 通用
   - interview_stage: 整体轮次，如 OA, Phone, VO, Onsite

2. **逐轮破译（rounds）**
   每轮一个对象，列出该轮的类型和具体内容。
   - type: 轮型由你根据帖子内容自行归纳，不限于常见几种，帖子里有什么轮次就写什么
   - topics: 该轮下的具体考点/题目/子话题，完全由你根据内容提炼，无固定词汇表
   - notes: 若有补充说明
   
   Coding 题写法（仅针对 topics 里的算法题）：
   - 能对应 LeetCode：直接写 LC题号
   - 不能明确对应：用最短语言描述题意，尽量 10 字以内

3. **detailed_summary**
   完整展开的总结，越详细越好。包括：
   - 流程、轮次、顺序
   - 每轮考了什么、难度、亮点
   - 题目细节、follow-up、变形
   - 对后端/系统设计/算法准备有价值的信息
   不要压缩成一行，要保留可检索的细节。

4. **confidence**: 0-1，你对破译结果的置信度

## 输出 JSON（仅 JSON，无 markdown）

严格要求：输出必须是合法 JSON，无尾部逗号，字符串内引号需转义。结构固定，内容由你根据帖子自由破译。以下仅为示例，type/topics 无任何预设枚举：

{{
  "company": "Meta",
  "direction": "MLE",
  "interview_stage": "VO",
  "rounds": [
    {{"type": "ML SD", "topics": ["地点推荐", "通知排序"], "notes": null}},
    {{"type": "BQ", "topics": ["pushback", "failure", "feedback"], "notes": null}},
    {{"type": "Coding", "topics": ["次大排列", "K路归并", "LC1239"], "notes": null}}
  ],
  "detailed_summary": "完整展开的破译结果...",
  "confidence": 0.85
}}

如果帖子信息不足或无法有效破译，仍输出 JSON，用 null 或空数组表示缺失，在 detailed_summary 中说明原因。
"""


def get_unparsed_thread_ids(conn):
    """Threads that have no interpreted result yet (none of their posts in interpreted_posts)."""
    c = conn.cursor()
    c.execute("""
        SELECT r.source_thread_id FROM raw_posts r
        WHERE r.source_thread_id IS NOT NULL
        GROUP BY r.source_thread_id
        HAVING NOT EXISTS (
            SELECT 1 FROM interpreted_posts i
            JOIN raw_posts r2 ON i.raw_post_id = r2.id
            WHERE r2.source_thread_id = r.source_thread_id
        )
        ORDER BY MIN(r.id) ASC
    """)
    return [row[0] for row in c.fetchall()]


def get_unparsed_orphan_post_ids(conn):
    """Posts with no source_thread_id (e.g. legacy), process as single-post 'threads'."""
    c = conn.cursor()
    c.execute("""
        SELECT r.id FROM raw_posts r
        LEFT JOIN interpreted_posts i ON r.id = i.raw_post_id
        WHERE r.source_thread_id IS NULL AND i.raw_post_id IS NULL
        ORDER BY r.id ASC
    """)
    return [row[0] for row in c.fetchall()]


def fetch_post(conn, post_id):
    """Single post by id."""
    c = conn.cursor()
    c.execute(
        "SELECT id, content, company, job_title, thread_title FROM raw_posts WHERE id = ?",
        (post_id,),
    )
    row = c.fetchone()
    return dict(zip(("id", "content", "company", "job_title", "thread_title"), row)) if row else None


def fetch_thread_posts(conn, thread_id):
    """All posts in a thread, ordered by id. Returns list of {id, content, company, job_title, thread_title}."""
    c = conn.cursor()
    c.execute(
        """SELECT id, content, company, job_title, thread_title
           FROM raw_posts
           WHERE source_thread_id = ?
           ORDER BY id ASC""",
        (thread_id,),
    )
    cols = ("id", "content", "company", "job_title", "thread_title")
    return [dict(zip(cols, row)) for row in c.fetchall()]


def _find_agent_binary():
    """Find Cursor Agent CLI binary. Prefers env vars, then PATH."""
    for env_key in ("INSTRUMENT_AGENT_PATH", "CURSOR_AGENT_PATH"):
        path = os.environ.get(env_key)
        if path and os.path.isfile(path):
            return path
    for name in ("agent", "cursor-agent"):
        found = shutil.which(name)
        if found:
            return found
    return None


def call_llm_via_cursor(content, company=None, job_title=None, thread_title=None):
    """Call LLM via Cursor Agent CLI.
    Format: agent -p "<prompt>" -f --output-format text --model composer-1.5 --mode ask
    No streaming (不需要 stream) - capture full output for JSON parsing.
    """
    agent_path = _find_agent_binary()
    if not agent_path:
        raise RuntimeError(
            "Cursor agent not found. Set CURSOR_AGENT_PATH or ensure 'agent' is in PATH. "
            "Install: https://cursor.com/docs/cli/using"
        )
    prompt = PROMPT.format(
        content=content,
        company=company or "unknown",
        job_title=job_title or "",
        thread_title=thread_title or "",
    )
    workspace = Path(__file__).parent.resolve()
    model = os.environ.get("CURSOR_AGENT_MODEL", "composer-1.5")
    mode = os.environ.get("CURSOR_AGENT_MODE", "ask")
    args = [
        agent_path,
        "-p",
        prompt,
        "-f",
        "--output-format",
        "text",
        "--model",
        model,
        "--mode",
        mode,
        "--trust",
        "--workspace",
        str(workspace),
    ]
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(workspace),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Cursor agent failed (exit {result.returncode}): {result.stderr or result.stdout}"
        )
    text = (result.stdout or "").strip()
    if not text:
        raise RuntimeError("Cursor agent returned empty output")
    return _parse_llm_json(text), model


def call_llm(content, company=None, job_title=None, thread_title=None):
    """Call LLM. Uses OPENAI_API_KEY (default) or ANTHROPIC_API_KEY."""
    prompt = PROMPT.format(
        content=content,
        company=company or "unknown",
        job_title=job_title or "",
        thread_title=thread_title or "",
    )

    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        client = anthropic.Anthropic()
        model = os.environ.get("KNOWLEDGE_MODEL", "claude-3-5-haiku-20241022")
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
    else:
        import openai
        client = openai.OpenAI()
        model = os.environ.get("KNOWLEDGE_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = resp.choices[0].message.content.strip()

    return _parse_llm_json(text), model


def _normalize_parsed(parsed):
    """Normalize parsed JSON: support both 扒帖 format and legacy format."""
    if "detailed_summary" in parsed or "rounds" in parsed:
        # 扒帖 format
        rounds = parsed.get("rounds") or []
        topic_parts = list(dict.fromkeys(r.get("type", "") for r in rounds if r.get("type")))
        topic = ",".join(topic_parts) if topic_parts else parsed.get("topic")
        coding_topics = []
        for r in rounds:
            if r.get("type", "").lower() in ("coding", "oa"):
                coding_topics.extend(r.get("topics") or [])
        interpreted_question = "; ".join(coding_topics) if coding_topics else parsed.get("interpreted_question")
        summary = parsed.get("detailed_summary") or parsed.get("summary")
        return {
            "company": parsed.get("company"),
            "interview_stage": parsed.get("interview_stage"),
            "topic": topic,
            "interpreted_question": interpreted_question,
            "question_family": parsed.get("question_family"),
            "summary": summary,
            "confidence": parsed.get("confidence"),
        }
    # Legacy format
    return {
        "company": parsed.get("company"),
        "interview_stage": parsed.get("interview_stage"),
        "topic": parsed.get("topic"),
        "interpreted_question": parsed.get("interpreted_question"),
        "question_family": parsed.get("question_family"),
        "summary": parsed.get("summary"),
        "confidence": parsed.get("confidence"),
    }


def insert_interpreted(conn, raw_post_id, parsed, model_name):
    norm = _normalize_parsed(parsed)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO interpreted_posts
        (raw_post_id, company, interview_stage, topic, interpreted_question, question_family, summary, confidence, parsed_json, model_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_post_id,
            norm["company"],
            norm["interview_stage"],
            norm["topic"],
            norm["interpreted_question"],
            norm["question_family"],
            norm["summary"],
            norm["confidence"],
            json.dumps(parsed),
            model_name,
        ),
    )
    conn.commit()


def init_interpreted_table(conn):
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS interpreted_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_post_id INTEGER NOT NULL UNIQUE,
            company TEXT,
            interview_stage TEXT,
            topic TEXT,
            interpreted_question TEXT,
            question_family TEXT,
            summary TEXT,
            confidence REAL,
            parsed_json TEXT,
            model_name TEXT,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (raw_post_id) REFERENCES raw_posts(id)
        )
    """)
    conn.commit()


def main():
    import argparse
    p = argparse.ArgumentParser(description="Parse raw_posts with LLM into interpreted_posts")
    p.add_argument("--limit", type=int, default=10, help="Max threads to process")
    p.add_argument("--all", action="store_true", help="Process all unparsed (ignore --limit)")
    p.add_argument("--dry-run", action="store_true", help="Don't call LLM or write DB")
    p.add_argument(
        "--cursor",
        action="store_true",
        dest="use_cursor",
        default=True,
        help="Use Cursor Agent CLI (default)",
    )
    p.add_argument(
        "--api",
        action="store_true",
        dest="use_api",
        help="Use OpenAI/Anthropic API instead of Cursor",
    )
    args = p.parse_args()
    limit = None if args.all else args.limit
    dry_run = args.dry_run
    use_cursor = args.use_cursor and not args.use_api

    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    init_interpreted_table(conn)

    if use_cursor:
        agent_path = _find_agent_binary()
        if not agent_path:
            print("ERROR: Cursor agent not found. Set CURSOR_AGENT_PATH or ensure 'agent' is in PATH.")
            sys.exit(1)
        print(f"Using Cursor Agent CLI: {agent_path}")

    thread_ids = get_unparsed_thread_ids(conn)
    orphan_ids = get_unparsed_orphan_post_ids(conn)
    # Work queue: (type, id) -> "thread"/"orphan", thread_id or post_id
    if limit is None:
        work = [("thread", tid) for tid in thread_ids]
        work.extend([("orphan", pid) for pid in orphan_ids])
    else:
        work = [("thread", tid) for tid in thread_ids[:limit]]
        remaining = limit - len(work)
        if remaining > 0:
            work.extend([("orphan", pid) for pid in orphan_ids[:remaining]])
    print(f"Found {len(thread_ids)} unparsed threads, {len(orphan_ids)} orphan posts. Processing {len(work)}.")

    for work_type, work_id in work:
        if work_type == "thread":
            posts = fetch_thread_posts(conn, work_id)
            if not posts:
                continue
            parts = []
            for i, p in enumerate(posts):
                if i == 0:
                    parts.append(p["content"])
                else:
                    parts.append(f"\n\n--- 楼内回复 ---\n\n{p['content']}")
            aggregated = "".join(parts)
            first, anchor_id = posts[0], posts[0]["id"]
            label = f"thread {work_id} ({len(posts)} posts)"
        else:
            first = fetch_post(conn, work_id)
            if not first:
                continue
            aggregated, anchor_id = first["content"], first["id"]
            label = f"orphan post {work_id}"
        print(f"  Parsing {label} ...")
        if dry_run:
            print("    [dry-run skip]")
            continue
        try:
            if use_cursor:
                parsed, model = call_llm_via_cursor(
                    aggregated,
                    company=first.get("company"),
                    job_title=first.get("job_title"),
                    thread_title=first.get("thread_title"),
                )
            else:
                parsed, model = call_llm(
                    aggregated,
                    company=first.get("company"),
                    job_title=first.get("job_title"),
                    thread_title=first.get("thread_title"),
                )
            insert_interpreted(conn, anchor_id, parsed, model)
            summary_preview = (parsed.get("detailed_summary") or parsed.get("summary") or "")[:60]
            print(f"    -> {parsed.get('company')} / {parsed.get('interview_stage')} / {summary_preview}...")
        except Exception as e:
            print(f"    ERROR: {e}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
