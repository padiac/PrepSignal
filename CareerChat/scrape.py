"""1point3acres forum-98 (职场达人) scraper.

Discuz! forum, GBK-encoded HTML, no login required. We hit the list page
to enumerate recent threads, then fetch each thread's full content
(主楼 + 回帖) for downstream LLM processing.

Usage (as library):
    from CareerChat.scrape import fetch_thread_list, fetch_thread_content
    threads = fetch_thread_list(page=1)
    content_md = fetch_thread_content(threads[0]["thread_id"])
"""
from __future__ import annotations

import random
import re
import time
from typing import Iterable

import requests
from bs4 import BeautifulSoup

BASE = "https://www.1point3acres.com/bbs"
LIST_URL = f"{BASE}/forum-98-{{page}}.html"
THREAD_URL = f"{BASE}/thread-{{tid}}-{{page}}-1.html"

# Be polite: rotate UA, respectful delays.
UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

REQUEST_TIMEOUT = 30
POLITE_SLEEP_RANGE = (2.0, 5.0)


def _fetch_html(url: str) -> str:
    """GET with UA rotation, decode GBK -> str."""
    headers = {
        "User-Agent": random.choice(UAS),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    }
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    # Discuz declares GBK; decode explicitly to avoid mojibake.
    try:
        return resp.content.decode("gbk", errors="replace")
    except Exception:
        return resp.text


def polite_sleep() -> None:
    time.sleep(random.uniform(*POLITE_SLEEP_RANGE))


def fetch_thread_list(page: int = 1) -> list[dict]:
    """Parse <tbody id=normalthread_xxx> rows from forum-98-{page}.html.

    Returns list of dicts (newest-replied-first per Discuz default sort):
        {
            "thread_id": int,
            "title": str,
            "url": str,
            "category": str | None,
            "author": str | None,
            "first_post_date": str | None,   # YYYY-MM-DD if HTML has title=
            "replies": int,
            "views": int,
            "last_post_iso": str | None,
        }
    """
    html = _fetch_html(LIST_URL.format(page=page))
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tbody in soup.select('tbody[id^="normalthread_"]'):
        tid_match = re.match(r"normalthread_(\d+)", tbody.get("id", ""))
        if not tid_match:
            continue
        tid = int(tid_match.group(1))

        # Title (the <a class="s xst"> link)
        title_a = tbody.select_one("a.s.xst")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)

        # Category tag (optional, e.g. 请问贵司, 找工求职)
        cat_em = tbody.select_one("em.specialtypexw a, em a")
        category = cat_em.get_text(strip=True) if cat_em else None

        # Author (first <cite> in row)
        cite = tbody.select_one("cite")
        author = cite.get_text(strip=True) if cite else None

        # First post date: first <em><span title="YYYY-M-D"> ...
        first_date = None
        em_spans = tbody.select("td.by em span[title]")
        if em_spans:
            first_date = em_spans[0].get("title")

        # Reply / view counts: <td class="num"><a>N</a><em>M</em></td>
        replies, views = 0, 0
        num_td = tbody.select_one("td.num")
        if num_td:
            ra = num_td.select_one("a")
            vm = num_td.select_one("em")
            try:
                replies = int(ra.get_text(strip=True)) if ra else 0
                views = int(vm.get_text(strip=True)) if vm else 0
            except ValueError:
                pass

        # Last post time (the bumped time, used for sort order)
        last_post_iso = None
        last_spans = tbody.select("td.by em a span[title]")
        if last_spans:
            last_post_iso = last_spans[-1].get("title")

        rows.append({
            "thread_id": tid,
            "title": title,
            "url": f"{BASE}/thread-{tid}-1-1.html",
            "category": category,
            "author": author,
            "first_post_date": first_date,
            "replies": replies,
            "views": views,
            "last_post_iso": last_post_iso,
        })
    return rows


def _extract_posts_from_page(html: str) -> list[dict]:
    """Parse posts from a thread page. Discuz uses <div id="post_XXX"> blocks
    containing <td class="t_f" id="postmessage_XXX"> with the body text.
    """
    soup = BeautifulSoup(html, "lxml")
    posts = []
    for post_div in soup.select('div[id^="post_"]'):
        # Author for this post
        author_el = post_div.select_one(".authi a, .authi cite")
        author = author_el.get_text(strip=True) if author_el else None

        # Post body
        body_td = post_div.select_one('td[id^="postmessage_"]')
        if not body_td:
            continue
        # Strip quoted blocks, signatures (keep it lean for the LLM)
        for tag in body_td.select(".quote, .signatures, .pcb script"):
            tag.decompose()
        text = body_td.get_text("\n", strip=True)
        if not text:
            continue
        posts.append({"author": author, "body": text})
    return posts


def fetch_thread_content(
    thread_id: int,
    max_pages: int = 3,
    max_chars: int = 12000,
) -> str:
    """Fetch a thread's posts (main + replies) and concat to a single markdown-ish string.

    Stops early once we've reached max_chars or max_pages.
    """
    chunks = []
    total_chars = 0
    for page in range(1, max_pages + 1):
        url = THREAD_URL.format(tid=thread_id, page=page)
        try:
            html = _fetch_html(url)
        except requests.HTTPError:
            break
        posts = _extract_posts_from_page(html)
        if not posts:
            break
        for i, p in enumerate(posts):
            label = "## 主楼" if (page == 1 and i == 0) else f"### 回复 (by {p['author'] or '匿名'})"
            chunk = f"{label}\n{p['body']}\n"
            chunks.append(chunk)
            total_chars += len(chunk)
            if total_chars >= max_chars:
                chunks.append("\n[...内容过长，已截断...]")
                return "\n".join(chunks)
        if page < max_pages:
            polite_sleep()
    return "\n".join(chunks)


def already_seen_ids(thread_ids: Iterable[int], db_path: str) -> set[int]:
    """Return subset that are already in seen_threads table."""
    import sqlite3
    ids = list(thread_ids)
    if not ids:
        return set()
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT thread_id FROM seen_threads WHERE thread_id IN ({placeholders})",
            ids,
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()
