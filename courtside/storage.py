"""Keep articles, story groups, and processing history in SQLite."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3


SCHEMA = """
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
"""


def save_run(result, database):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        with connection:
            run_id = connection.execute(
                "INSERT INTO processing_runs (source, window_start, window_end, input_complete, result_json) VALUES (?, ?, ?, ?, ?)",
                (result["source"], result["window_start"], result["window_end"], result["input_complete"], json.dumps(result))).lastrowid
            article_ids = {}
            for article in result["articles"]:
                connection.execute(
                    "INSERT INTO articles (canonical_url, original_url, publisher_name, published_at, collected_at, article_json) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(canonical_url) DO UPDATE SET original_url=excluded.original_url, publisher_name=excluded.publisher_name, published_at=excluded.published_at, collected_at=excluded.collected_at, article_json=excluded.article_json",
                    (article["canonical_url"], article["url"], article["publisher_name"], article["published_at"], article["collected_at"], json.dumps(article)))
                article_ids[article["canonical_url"]] = connection.execute(
                    "SELECT id FROM articles WHERE canonical_url = ?", (article["canonical_url"],)).fetchone()[0]
            for story in result["stories"]:
                connection.execute("INSERT INTO story_clusters VALUES (?, ?, ?)", (run_id, story["id"], json.dumps(story)))
                for url in story["article_urls"]:
                    connection.execute("INSERT INTO story_articles VALUES (?, ?, ?)", (run_id, story["id"], article_ids[url]))
    return run_id
