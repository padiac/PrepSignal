# Interview Trend Agent System Plan

## Goal

Build a lightweight interview-intelligence system that focuses on:

- collecting raw interview posts every day
- using an LLM to do **one-shot rough interpretation**
- discovering **high-frequency questions and trends**
- supporting Telegram **daily digest** and **interactive query**
- keeping the bot **strictly limited to DB / knowledge access only**

This system does **not** aim for perfect canonical mapping such as exact LeetCode IDs.  
If a post is vague and the model interprets it a bit wrong, that is acceptable.  
The real value is finding patterns like:

- what Google has been asking recently
- whether Meta and Google both asked similar aggregation-style questions
- whether system design frequency is increasing
- which topics are worth prioritizing

---

## Design Principles

### 1. Collection layer should stay dumb
The collection layer only stores raw facts.

It should not:
- summarize
- classify
- normalize aliases
- infer problem IDs

It should only store:
- post ID
- raw content
- post date
- optional source URL / source site

This keeps the pipeline stable and easy to replay.

### 2. Knowledge layer should do one-shot rough understanding
The knowledge layer uses an LLM to interpret each raw post once.

It should extract:
- company
- interview stage if possible
- topic
- rough question meaning
- rough question family
- summary
- confidence

This is intentionally rough and pragmatic.

### 3. Broadcast / query layer should only aggregate and answer
The Telegram-facing bot should not parse raw posts directly.

It should:
- read interpreted results
- generate daily digests
- answer trend queries
- compare companies
- summarize patterns

### 4. Accuracy is useful, perfection is unnecessary
Interview posts are often vague, incomplete, or based on memory.  
This system should optimize for:

- broad coverage
- speed
- trend usefulness

not for exact forensic correctness.

### 5. Security boundary must be narrow
The Telegram bot must not access anything except the interview knowledge service / database.

It must not have:
- shell execution
- filesystem access
- browser access
- arbitrary tool access
- write access outside its allowed tables or APIs

---

## System Architecture

```text
Chrome Extension / Relay
    -> Ingestion API
    -> raw_posts

Knowledge Bot / Worker
    -> reads raw_posts
    -> LLM one-shot parse
    -> writes interpreted_posts

Query & Broadcast Bot
    -> reads interpreted_posts
    -> answers Telegram queries
    -> sends daily digest
```

---

## Components

## 1. Collection Layer

### Responsibility

Collect raw interview posts from the source and store them unchanged.

### Input source

- Chrome extension
- Chrome relay
- manual or semi-automated scrape pipeline

### Output table

- `raw_posts`

### Stored fields

- `source_site`
- `source_post_id`
- `source_url`
- `content`
- `created_at`
- `ingested_at`

### Important rule

Do **not** put AI logic here.

This layer should remain boring and reliable.

---

## 2. Knowledge Layer

### Responsibility

Interpret each raw post once using an LLM and produce a rough structured record.

### Input

- unparsed rows in `raw_posts`

### Output

- `interpreted_posts`

### What it extracts

- company
- interview stage
- topic
- interpreted question meaning
- question family
- summary
- confidence
- raw JSON parse result
- model name

### Why this layer exists

Without this layer, every query would need to re-read and re-interpret all raw posts.  
That would be slow, expensive, and unstable.

By storing one-shot interpretations, later queries can focus on:

- statistics
- search
- comparison
- synthesis

### Accepted limitations

- interpretation may drift
- posts may be ambiguous
- the model may be wrong sometimes

This is acceptable because the system is mainly used for:

- trend detection
- high-frequency topic discovery
- preparation prioritization

not exact archival truth.

---

## 3. Broadcast / Query Layer

### Responsibility

Provide two user-facing capabilities:

#### A. Daily broadcast
Examples:

- today’s new Google / Meta / Microsoft interview post summary
- top question families today
- notable trend changes
- short personalized recommendation later if needed

#### B. Interactive query
Examples:

- “Meta 最近考了 ad agg，Google 最近有没有类似题？”
- “最近 Google 高频题有哪些？”
- “最近 system design 有没有增多？”
- “最近有哪些值得特别注意的动向？”

### Key rule

This bot reads interpreted results only.  
It should not parse raw content on demand unless absolutely necessary.

---

# Database Design

## Table 1: `raw_posts`

```sql
CREATE TABLE raw_posts (
    id BIGSERIAL PRIMARY KEY,
    source_site TEXT,
    source_post_id TEXT NOT NULL,
    source_url TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_site, source_post_id)
);
```

### Notes

This table is the source of truth for collected posts.

It stores:
- raw content
- source metadata
- timestamps

It stores no AI interpretation.

---

## Table 2: `interpreted_posts`

```sql
CREATE TABLE interpreted_posts (
    id BIGSERIAL PRIMARY KEY,
    raw_post_id BIGINT NOT NULL REFERENCES raw_posts(id) ON DELETE CASCADE,
    company TEXT,
    interview_stage TEXT,
    topic TEXT,
    interpreted_question TEXT,
    question_family TEXT,
    summary TEXT,
    confidence REAL,
    parsed_json JSONB,
    model_name TEXT,
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (raw_post_id)
);
```

### Field meaning

- `company`  
  Example: `Google`, `Meta`, `Microsoft`

- `interview_stage`  
  Example: `oa`, `phone`, `onsite`, `unknown`

- `topic`  
  Example: `coding`, `system_design`, `behavioral`, `ml`, `infra`, `unknown`

- `interpreted_question`  
  Example: `likely next permutation style problem`

- `question_family`  
  Example: `permutation`, `aggregation`, `graph`, `cache`, `system_design`

- `summary`  
  A short natural-language summary of the post

- `confidence`  
  Float from 0 to 1

- `parsed_json`  
  Full structured LLM response for debugging and future extension

- `model_name`  
  Example: `openai/gpt-5`, `anthropic/claude-sonnet-4`

---

## Optional Table 3: `daily_company_stats`

This is optional for later optimization.

```sql
CREATE TABLE daily_company_stats (
    stat_date DATE NOT NULL,
    company TEXT NOT NULL,
    topic TEXT,
    question_family TEXT,
    post_count INT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (stat_date, company, topic, question_family)
);
```

Use this only if the dataset grows large and repeated aggregation becomes expensive.

---

# AI Parsing Strategy

## Objective

Use the LLM once per raw post to create a useful rough interpretation.

## Required output format

Example JSON output:

```json
{
  "company": "Google",
  "interview_stage": "onsite",
  "topic": "coding",
  "interpreted_question": "likely next permutation style problem",
  "question_family": "permutation",
  "summary": "Poster described a coding round involving finding the next larger arrangement of numbers, but did not remember the exact original problem.",
  "confidence": 0.64
}
```

## Important implementation rule

Do not require exact LeetCode IDs.

Bad goal:
- “must map to lc31 or fail”

Good goal:
- “roughly classify as next-permutation-like problem”

## Why this is the right tradeoff

Interview posts are often vague, compressed, or remembered imperfectly.  
The system is supposed to discover patterns, not certify truth like a court transcript.

---

# Query Flow

## Example question

> Meta 最近考了 ad agg，Google 最近有没有类似题？

## Processing flow

### Step 1: query understanding
LLM converts the user question into structured intent:

- companies: `Meta`, `Google`
- concept: `aggregation-like coding problem`
- time window: recent / 30 days
- topic: coding

### Step 2: retrieval
The query service searches `interpreted_posts` using:

- company filters
- date window
- topic filter
- question family or interpreted-question semantic matching

### Step 3: answer synthesis
LLM summarizes the matched records into a readable answer:

- whether similar questions appeared
- rough frequency
- any trend difference
- representative evidence posts

## Another example

> 最近 Google 高频题有哪些，有没有什么值得注意的动向？

The query service should retrieve:

- recent Google interpreted posts
- top question families
- topic distribution
- week-over-week changes if possible

Then the LLM answers with:

- most common recent categories
- notable increase or decrease
- recommended preparation focus

---

# Bot Design

## Bot 1: Knowledge Bot

### Type

Internal worker bot or background agent

### Responsibilities

- poll unparsed `raw_posts`
- call the LLM
- validate JSON output
- insert into `interpreted_posts`

### Non-responsibilities

- no Telegram
- no direct user chat
- no daily broadcast
- no external-facing query

### Why separate it

This bot solves a different problem:

- understanding one post at a time

That is different from:

- summarizing many posts together

Keeping them separate makes prompts, logging, and debugging much cleaner.

---

## Bot 2: Query & Broadcast Bot

### Type

Telegram-facing bot

### Responsibilities

- answer user questions
- provide daily digests
- summarize recent trends
- compare companies
- highlight high-frequency topics

### Non-responsibilities

- no raw scraping
- no direct parsing pipeline
- no arbitrary system access

---

# Security Plan

This is extremely important.

The Telegram bot should be allowed to access **only the interview knowledge service or read-only DB interface**.

## Allowed capabilities

- `search_interviews`
- `get_daily_digest`
- optional `health_check`

## Disallowed capabilities

- shell / exec
- filesystem read / write
- browser
- patching / editing files
- process control
- arbitrary network exploration
- unrelated internal tools

## Database account split

### Knowledge bot DB account
Permissions:
- read `raw_posts`
- write `interpreted_posts`

### Query bot DB account
Permissions:
- read `interpreted_posts`
- optionally read aggregate views
- no write access to raw collection data

---

# API / Tool Interface Design

## Ingestion API

### Endpoint
`POST /posts`

### Request body

```json
{
  "source_site": "1point3acres",
  "source_post_id": "abc123",
  "source_url": "https://example.com/post/abc123",
  "content": "raw post content ...",
  "created_at": "2026-03-11T01:00:00Z"
}
```

### Behavior

- deduplicate by `(source_site, source_post_id)`
- insert into `raw_posts`
- return inserted or existing status

---

## Knowledge service function

### `parse_raw_post(raw_post_id)`

#### Input

```json
{
  "raw_post_id": 123
}
```

#### Behavior

- fetch raw post
- send to LLM with strict JSON schema
- validate output
- insert one row into `interpreted_posts`

#### Output

```json
{
  "raw_post_id": 123,
  "status": "ok",
  "company": "Google",
  "topic": "coding"
}
```

---

## Query service function 1

### `search_interviews`

#### Input

```json
{
  "companies": ["Meta", "Google"],
  "question_hint": "aggregation-like problem",
  "topic": "coding",
  "days": 30,
  "limit": 20
}
```

#### Output

```json
{
  "matches": [
    {
      "company": "Meta",
      "created_at": "2026-03-08T10:00:00Z",
      "interpreted_question": "ad aggregation style coding problem",
      "question_family": "aggregation",
      "summary": "..."
    }
  ]
}
```

---

## Query service function 2

### `get_daily_digest`

#### Input

```json
{
  "date": "2026-03-11",
  "companies": ["Google", "Meta", "Microsoft"]
}
```

#### Output

```json
{
  "date": "2026-03-11",
  "total_posts": 18,
  "company_breakdown": [
    { "company": "Google", "count": 7 },
    { "company": "Meta", "count": 6 }
  ],
  "top_question_families": [
    { "family": "aggregation", "count": 5 },
    { "family": "graph", "count": 4 }
  ],
  "notable_trends": [
    "Google system design mentions increased this week"
  ]
}
```

---

# Prompting Strategy

## Knowledge bot prompt

Purpose:
- parse one raw interview post into rough structured meaning

Requirements:
- strict JSON output
- no long reasoning
- allow unknown values
- tolerate ambiguity
- do not force exact LeetCode mapping

### Recommended behavior rules

- infer company if reasonably clear
- infer topic from context
- describe the problem naturally if exact identity is unclear
- assign a rough `question_family`
- return lower confidence when post is vague

---

## Query bot prompt

Purpose:
- understand user query
- decide retrieval parameters
- summarize results faithfully

Requirements:
- do not invent matches
- distinguish between “found evidence” and “weak similarity”
- prioritize trend usefulness over overconfident precision

---

# Suggested Folder Structure

```text
interview-agent/
├─ apps/
│  ├─ ingestion-api/
│  │  ├─ main.py
│  │  ├─ routes.py
│  │  └─ schemas.py
│  ├─ knowledge-worker/
│  │  ├─ main.py
│  │  ├─ parser.py
│  │  ├─ prompts.py
│  │  └─ repository.py
│  └─ query-service/
│     ├─ main.py
│     ├─ tools.py
│     ├─ digest.py
│     └─ repository.py
├─ db/
│  ├─ migrations/
│  │  ├─ 001_create_raw_posts.sql
│  │  ├─ 002_create_interpreted_posts.sql
│  │  └─ 003_indexes.sql
│  └─ seed/
├─ openclaw/
│  ├─ knowledge-agent.jsonc
│  ├─ query-agent.jsonc
│  └─ cron-examples.md
├─ shared/
│  ├─ db.py
│  ├─ models.py
│  └─ config.py
├─ tests/
│  ├─ test_parser.py
│  ├─ test_search.py
│  └─ test_digest.py
└─ README.md
```

---

# Recommended Indexes

```sql
CREATE INDEX idx_raw_posts_created_at
ON raw_posts(created_at DESC);

CREATE INDEX idx_interpreted_posts_company_created_at
ON interpreted_posts(company, parsed_at DESC);

CREATE INDEX idx_interpreted_posts_topic
ON interpreted_posts(topic);

CREATE INDEX idx_interpreted_posts_question_family
ON interpreted_posts(question_family);
```

If needed later, add full-text or vector search.  
Do not start with that. Start simple.

---

# Phase Plan

## Phase 1: Minimum Viable System

### Build first

- ingestion API
- `raw_posts` table
- knowledge worker
- `interpreted_posts` table
- query service with two functions:
  - `search_interviews`
  - `get_daily_digest`
- Telegram query bot
- one daily digest job

### Do not build yet

- vector DB
- alias dictionaries
- exact LeetCode mapping
- complex reranking
- personalized recommendation engine
- multi-model voting

This phase is about making the system alive.

---

## Phase 2: Better Query Quality

Add:
- query rewriting
- better date range handling
- company comparison
- topic filtering
- trend summaries over time windows

---

## Phase 3: Personalized Recommendation

Add:
- user preference profile
- followed companies
- followed topics
- personal digest customization

Only do this after the core system is stable.

---

# Practical Tradeoff Summary

## Things we intentionally do

- use one-shot rough interpretation
- accept ambiguity
- focus on high-frequency topics and trends
- separate parsing from user-facing Q&A
- keep Telegram bot heavily restricted

## Things we intentionally do not do

- exact canonical problem ID mapping
- rigid alias systems
- over-engineered ontology
- perfect correctness
- full autonomous agent access

This is the right tradeoff because the business value is:

- “what is being asked often lately?”
- “what direction is changing?”
- “what should I prioritize?”

not:
- “can I certify the exact original problem with absolute certainty?”

---

# Cursor Implementation Prompt

Use this prompt in Cursor to scaffold the project:

```text
Build a Python project for an interview-trend Telegram agent system.

Requirements:

1. There are three components:
   - ingestion API: accepts raw scraped posts from a Chrome extension
   - knowledge worker: reads raw posts from database, uses an LLM to do one-shot interpretation, and stores structured results
   - query service: exposes read-only functions for daily digest and semantic interview search

2. Database schema:
   - raw_posts(id, source_site, source_post_id, source_url, content, created_at, ingested_at)
   - interpreted_posts(id, raw_post_id, company, interview_stage, topic, interpreted_question, question_family, summary, confidence, parsed_json, model_name, parsed_at)

3. The knowledge worker should:
   - poll for raw_posts not yet parsed
   - call an LLM with a strict JSON response format
   - extract company, topic, interpreted_question, question_family, summary, confidence
   - insert one row into interpreted_posts for each raw_post

4. The query service should provide:
   - search_interviews(companies, question_hint, topic, days, limit)
   - get_daily_digest(date, companies)

5. Use PostgreSQL.
6. Use SQLAlchemy or psycopg.
7. Keep the code modular and production-oriented.
8. Add migration SQL files.
9. Add tests for parser output validation and query logic.
10. Do not implement alias dictionaries or exact LeetCode mapping. The system should rely on LLM one-shot interpretation only.

Also generate:
- project folder structure
- initial SQL migrations
- Pydantic schemas
- parser prompt template
- repository layer
- stub query functions
- README with local run instructions
```

---

# Final Recommendation

The best next step is not polishing Telegram wording.

The best next step is:

1. create `raw_posts`
2. create `interpreted_posts`
3. build the knowledge worker
4. build the read-only query service
5. connect the Telegram bot only to those read-only functions

Once that works, the system is alive.

Then you can slowly grow more tentacles onto the lobster.
