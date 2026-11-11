CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    canonical_url TEXT NOT NULL UNIQUE,
    original_url TEXT NOT NULL,
    publisher_name TEXT NOT NULL,
    published_at TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    article_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processing_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    input_complete INTEGER NOT NULL,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS story_clusters (
    run_id INTEGER NOT NULL REFERENCES processing_runs(id),
    story_id TEXT NOT NULL,
    story_json TEXT NOT NULL,
    PRIMARY KEY (run_id, story_id)
);
CREATE TABLE IF NOT EXISTS story_articles (
    run_id INTEGER NOT NULL,
    story_id TEXT NOT NULL,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    FOREIGN KEY (run_id, story_id) REFERENCES story_clusters(run_id, story_id),
    PRIMARY KEY (run_id, story_id, article_id)
);
CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY,
    processing_run_id INTEGER REFERENCES processing_runs(id),
    as_of TEXT NOT NULL,
    experimental INTEGER NOT NULL,
    briefing_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS story_scores (
    briefing_id INTEGER NOT NULL REFERENCES briefings(id),
    story_id TEXT NOT NULL,
    rank INTEGER,
    score REAL NOT NULL,
    eligible INTEGER NOT NULL,
    score_json TEXT NOT NULL,
    PRIMARY KEY (briefing_id, story_id)
);
CREATE TABLE IF NOT EXISTS refresh_attempts (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    lease_until TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    requests_used INTEGER NOT NULL,
    briefing_id INTEGER REFERENCES briefings(id),
    error TEXT
);
CREATE TABLE IF NOT EXISTS investigations (
    briefing_id INTEGER NOT NULL,
    story_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    investigation_json TEXT NOT NULL,
    FOREIGN KEY (briefing_id, story_id) REFERENCES story_scores(briefing_id, story_id),
    PRIMARY KEY (briefing_id, story_id)
);
CREATE TABLE IF NOT EXISTS sample_agent_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    lease_until TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    requests_used INTEGER NOT NULL,
    result_json TEXT,
    error TEXT
);
