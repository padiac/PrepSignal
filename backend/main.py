from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import datetime
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PostSchema(BaseModel):
    source_site: str
    source_post_id: str
    source_thread_id: Optional[str] = None
    source_url: str
    content: str
    created_at: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    thread_title: Optional[str] = None
    thread_metadata: Optional[str] = None  # Full line: "码农类General 硕士 全职@sig - 内推 - Onsite | ..."

class ThreadIdsSchema(BaseModel):
    thread_ids: list[str]

DB_PATH = "raw_posts.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Add column if not exists (for backward compatibility if run_backend restarts)
    for col in ("source_thread_id", "company", "job_title", "thread_title", "thread_metadata"):
        try:
            c.execute(f"ALTER TABLE raw_posts ADD COLUMN {col} TEXT")
        except Exception:
            pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS raw_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_site TEXT,
            source_post_id TEXT,
            source_thread_id TEXT,
            source_url TEXT,
            content TEXT,
            created_at TEXT,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_site, source_post_id)
        )
    ''')
    c.execute('''
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
    ''')
    conn.commit()
    conn.close()

init_db()

@app.get("/")
def root():
    return {"message": "PrepSignal API", "endpoints": {"posts": "/posts", "interpreted": "/interpreted", "thread_post_counts": "POST /threads/post_counts", "docs": "/docs"}}

@app.post("/posts")
def ingest_post(post: PostSchema):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO raw_posts 
            (source_site, source_post_id, source_thread_id, source_url, content, created_at, company, job_title, thread_title, thread_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_site, source_post_id) DO UPDATE SET
                content = excluded.content,
                company = excluded.company,
                job_title = excluded.job_title,
                thread_title = excluded.thread_title,
                thread_metadata = excluded.thread_metadata,
                ingested_at = CURRENT_TIMESTAMP
        ''', (post.source_site, post.source_post_id, post.source_thread_id, post.source_url, post.content, post.created_at, post.company, post.job_title, post.thread_title, post.thread_metadata))
        conn.commit()
        inserted = True
    except Exception as e:
        print(f"DB Error: {e}")
        inserted = False
    finally:
        conn.close()
        
    return {"status": "ok", "inserted": inserted}

@app.post("/threads/post_counts")
def get_thread_post_counts(body: ThreadIdsSchema):
    """Return post count per thread_id from DB. Used by extension to skip re-queueing threads with no new replies."""
    thread_ids = body.thread_ids
    if not thread_ids:
        return {}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ",".join("?" * len(thread_ids))
    c.execute(
        f"SELECT source_thread_id, COUNT(*) FROM raw_posts WHERE source_site='1point3acres' AND source_thread_id IN ({placeholders}) GROUP BY source_thread_id",
        thread_ids,
    )
    result = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    # Include threads we have no record of as 0
    return {tid: result.get(tid, 0) for tid in thread_ids}

@app.get("/posts")
def get_posts(limit: int = 50, offset: int = 0):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM raw_posts ORDER BY id DESC LIMIT ? OFFSET ?', (limit, offset))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

@app.get("/interpreted")
def get_interpreted(limit: int = 50, offset: int = 0):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute(
            '''SELECT i.*, r.content as raw_content, r.company as raw_company, r.source_url
               FROM interpreted_posts i
               JOIN raw_posts r ON i.raw_post_id = r.id
               ORDER BY i.parsed_at DESC LIMIT ? OFFSET ?''',
            (limit, offset),
        )
        rows = [dict(row) for row in c.fetchall()]
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return rows
