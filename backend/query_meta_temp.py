#!/usr/bin/env python3
"""Temporary script to query Meta interview questions from raw_posts.db"""
import sqlite3
import json

DB = "/home/padiac/PrepSignal/backend/raw_posts.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

# 1. raw_posts - Meta by company/thread_title/content
c.execute("""
    SELECT id, content, company, thread_title, thread_metadata, created_at 
    FROM raw_posts 
    WHERE (company IS NOT NULL AND (LOWER(company) LIKE '%meta%' OR company LIKE '%Meta%'))
       OR (thread_title IS NOT NULL AND (LOWER(thread_title) LIKE '%meta%'))
       OR (content LIKE '%Meta%' OR LOWER(content) LIKE '%meta onsite%' OR LOWER(content) LIKE '%meta 面经%')
    ORDER BY id DESC 
    LIMIT 100
""")
raw = c.fetchall()

# 2. interpreted_posts for Meta
try:
    c.execute("""
        SELECT i.company, i.interview_stage, i.topic, i.interpreted_question, i.question_family, i.summary, r.content
        FROM interpreted_posts i
        JOIN raw_posts r ON i.raw_post_id = r.id
        WHERE LOWER(COALESCE(i.company,'')) LIKE '%meta%' OR LOWER(COALESCE(r.company,'')) LIKE '%meta%'
        ORDER BY i.parsed_at DESC
        LIMIT 50
    """)
    interpreted = c.fetchall()
except sqlite3.OperationalError:
    interpreted = []

conn.close()

# Output
print("=== RAW POSTS (Meta-related) ===")
print(f"Count: {len(raw)}\n")
for row in raw[:15]:
    print(f"ID:{row[0]} | Company:{row[2]} | Title:{row[3][:60] if row[3] else 'N/A'}...")
    print(f"  Content snippet: {(row[1] or '')[:200]}...")
    print()

print("\n=== INTERPRETED POSTS (Meta) ===")
print(f"Count: {len(interpreted)}\n")
for row in interpreted[:20]:
    print(f"Company:{row[0]} | Stage:{row[1]} | Topic:{row[2]}")
    print(f"  Q: {row[3]}")
    print(f"  Family: {row[4]} | Summary: {row[5]}")
    print()
