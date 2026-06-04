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
                                         --   worth = content valuable, enriched_md generated
                                         --   skip  = no content value, no enriched_md
                                         --   baseline = pre-marked as seen, not processed
    reason           TEXT,              -- LLM's worth/skip reason / error msg
    enriched_md      TEXT,              -- the markdown (always present when decision=worth,
                                         -- regardless of whether it was pushed to telegram)
    model_name       TEXT,
    push_decision    TEXT,              -- 'pushed' | 'archived' | NULL (if decision != worth)
                                         --   pushed   = high engagement, sent to telegram
                                         --   archived = worth content but low engagement, DB only
    push_reason      TEXT,              -- LLM's reason for push/archive
    sent_at          TIMESTAMP          -- when telegram delivery succeeded (NULL if archived)
);
CREATE INDEX IF NOT EXISTS idx_first_seen ON seen_threads(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_decision ON seen_threads(decision);
-- idx_push_decision created in pipeline.py:ensure_db() after the column is guaranteed to exist
-- (CREATE INDEX here would fail on pre-existing DBs that don't yet have the column)
