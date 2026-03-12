-- interpreted_posts: AI-parsed knowledge base (扒帖破译) derived from raw_posts
-- parsed_json 格式：{ company, direction, interview_stage, rounds: [{type, topics[], notes}], detailed_summary, confidence }
-- summary 存 detailed_summary；topic 从 rounds 推导；interpreted_question 存 Coding 题
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
);
