"""Keep articles, story groups, and processing history in SQLite."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
from datetime import timedelta

from scripts.validate_gdelt import format_time
from .stories import parse_date


SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


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


def save_briefing(briefing, database):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        run_id = briefing.get("processing_run_id")
        if run_id is not None and connection.execute("SELECT id FROM processing_runs WHERE id = ?", (run_id,)).fetchone() is None:
            raise ValueError("Processing run not found in this database. Process the articles into the same database first.")
        with connection:
            briefing_id = connection.execute(
                "INSERT INTO briefings (processing_run_id, as_of, experimental, briefing_json) VALUES (?, ?, ?, ?)",
                (run_id, briefing["as_of"], briefing["experimental"], json.dumps(briefing))).lastrowid
            for story in briefing["candidates"]:
                connection.execute("INSERT INTO story_scores VALUES (?, ?, ?, ?, ?, ?)",
                                   (briefing_id, story["id"], story["rank"], story["score"], story["eligible"], json.dumps(story)))
                if story.get("investigation"):
                    investigation = story["investigation"]
                    connection.execute("INSERT INTO investigations VALUES (?, ?, ?, ?, ?)",
                                       (briefing_id, story["id"], investigation.get("provider", "unavailable"),
                                        investigation["status"], json.dumps(investigation)))
    return briefing_id


def initialize_database(database):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(SCHEMA)


def read_briefings(database, mode, limit=10, briefing_id=None):
    query = "SELECT id, briefing_json FROM briefings WHERE COALESCE(json_extract(briefing_json, '$.data_mode'), 'live') = ?"
    params = [mode]
    if briefing_id is not None:
        query += " AND id = ?"
        params.append(briefing_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(query, params).fetchall()
    return [{**json.loads(payload), "briefing_id": saved_id, "data_mode": mode} for saved_id, payload in rows]


def read_run(database, run_id):
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute("SELECT result_json FROM processing_runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row[0]) if row else None


def read_refreshes(database, mode, limit=1):
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM refresh_attempts WHERE mode = ? ORDER BY id DESC LIMIT ?", (mode, limit)).fetchall()
    return [dict(row) for row in rows]


def start_refresh(database, mode, now, requests, max_seconds=90):
    timestamp = format_time(now)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE refresh_attempts SET status='failed', completed_at=?, error='Previous refresh was interrupted' WHERE status='running' AND lease_until <= ?", (timestamp, timestamp))
        if connection.execute("SELECT id FROM refresh_attempts WHERE status='running'").fetchone():
            return dict(status_code=409, error="A refresh is already running", retry_after=5)
        if mode == "live":
            last = connection.execute("SELECT started_at FROM refresh_attempts WHERE mode='live' AND requests_used > 0 ORDER BY id DESC LIMIT 1").fetchone()
            if last:
                remaining = 60 - (now - parse_date(last[0])).total_seconds()
                if remaining > 0:
                    return dict(status_code=429, error="Wait a minute between live refreshes", retry_after=max(1, int(remaining) + 1))
            today = format_time(now.replace(hour=0, minute=0, second=0, microsecond=0))
            used = connection.execute("SELECT COALESCE(SUM(requests_used), 0) FROM refresh_attempts WHERE mode='live' AND started_at >= ?", (today,)).fetchone()[0]
            if used + requests > 30:
                next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                return dict(status_code=429, error="This app's daily limit of 30 source requests has been reached",
                            retry_after=max(1, int((next_day - now).total_seconds()) + 1))
        refresh_id = connection.execute(
            "INSERT INTO refresh_attempts (mode, started_at, lease_until, status, requests_used) VALUES (?, ?, ?, 'running', ?)",
            (mode, timestamp, format_time(now + timedelta(seconds=max_seconds + 15)), requests)).lastrowid
    return dict(id=refresh_id)


def finish_refresh(database, refresh_id, now, status, requests_used, briefing_id=None, error=None):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("UPDATE refresh_attempts SET completed_at=?, status=?, requests_used=?, briefing_id=?, error=? WHERE id=?",
                           (format_time(now), status, requests_used, briefing_id, error, refresh_id))


def start_sample_agent(database, now):
    timestamp = format_time(now)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE sample_agent_runs SET status='interrupted', completed_at=?, error='Previous run was interrupted' WHERE status='running' AND lease_until <= ?", (timestamp, timestamp))
        running = connection.execute("SELECT id FROM sample_agent_runs WHERE status='running'").fetchone()
        if running:
            return dict(status_code=409, error="A sample investigation is already running", retry_after=5)
        latest = connection.execute("SELECT started_at FROM sample_agent_runs ORDER BY id DESC LIMIT 1").fetchone()
        if latest:
            remaining = 60 - (now - parse_date(latest[0])).total_seconds()
            if remaining > 0:
                return dict(status_code=429, error="Wait a minute before another sample investigation", retry_after=max(1, int(remaining) + 1))
        today = format_time(now.replace(hour=0, minute=0, second=0, microsecond=0))
        used = connection.execute("SELECT COALESCE(SUM(requests_used), 0) FROM sample_agent_runs WHERE started_at >= ?", (today,)).fetchone()[0]
        if used + 5 > 15:
            next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            return dict(status_code=429, error="The daily limit of 15 sample AI requests has been reached", retry_after=max(1, int((next_day - now).total_seconds()) + 1))
        run_id = connection.execute("INSERT INTO sample_agent_runs (started_at, lease_until, status, requests_used) VALUES (?, ?, 'running', 5)", (timestamp, format_time(now + timedelta(seconds=45)))).lastrowid
    return dict(id=run_id)


def finish_sample_agent(database, run_id, now, status, requests_used, result=None, error=None):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("UPDATE sample_agent_runs SET completed_at=?, status=?, requests_used=?, result_json=?, error=? WHERE id=?",
                           (format_time(now), status, requests_used, json.dumps(result) if result is not None else None, error, run_id))
