-- CareerChat: track which forum threads we've processed, dedup + history
CREATE TABLE IF NOT EXISTS seen_threads (
    thread_id        INTEGER PRIMARY KEY,
    title            TEXT NOT NULL,
    url              TEXT NOT NULL,
    category         TEXT,              -- forum category tag (请问贵司 / 找工求职 etc)
    author           TEXT,
    first_post_date  TEXT,              -- ISO datetime if known, else freeform
    first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decision         TEXT NOT NULL,     -- 'worth' | 'skip' | 'error' | 'baseline'
    reason           TEXT,              -- LLM's skip reason / error msg
    enriched_md      TEXT,              -- the markdown sent to telegram (if worth)
    model_name       TEXT,
    sent_at          TIMESTAMP          -- when telegram delivery succeeded
);
CREATE INDEX IF NOT EXISTS idx_first_seen ON seen_threads(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_decision ON seen_threads(decision);
