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

DB_PATH = "raw_posts.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Add column if not exists (for backward compatibility if run_backend restarts)
    try:
        c.execute('ALTER TABLE raw_posts ADD COLUMN source_thread_id TEXT')
    except:
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
    conn.commit()
    conn.close()

init_db()

@app.post("/posts")
def ingest_post(post: PostSchema):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO raw_posts 
            (source_site, source_post_id, source_thread_id, source_url, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_site, source_post_id) DO UPDATE SET
                content = excluded.content,
                ingested_at = CURRENT_TIMESTAMP
        ''', (post.source_site, post.source_post_id, post.source_thread_id, post.source_url, post.content, post.created_at))
        conn.commit()
        inserted = True
    except Exception as e:
        print(f"DB Error: {e}")
        inserted = False
    finally:
        conn.close()
        
    return {"status": "ok", "inserted": inserted}

@app.get("/posts")
def get_posts(limit: int = 50, offset: int = 0):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM raw_posts ORDER BY id DESC LIMIT ? OFFSET ?', (limit, offset))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows
