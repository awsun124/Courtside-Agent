"""Connect news collection, story processing, ranking, and saved briefings."""
from argparse import Namespace
from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.validate_gnews import load_api_key, SourceError
from .sources import collect_sources, DEFAULT_SOURCES
from .feeds import load_sources
from .free_news import load_key as load_free_news_key, load_settings as load_free_news_settings
from .ranking import RankingSettings, rank_stories
from .sample_data import sample_report
from .investigate import add_investigations
from .stories import process_report, parse_date
from .storage import (finish_refresh, initialize_database, read_briefings, read_refreshes,
                      read_run, save_briefing, save_run, start_refresh)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RefreshError(Exception):
    def __init__(self, status_code, message, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class NewsService:
    def __init__(self, database, env_file=None, settings_file=None, collector=None, clock=None, investigation_file=None, sources_file=None):
        self.database = Path(database)
        self.env_file = Path(env_file or PROJECT_ROOT / ".env")
        self.settings_file = Path(settings_file or PROJECT_ROOT / "config/ranking.json")
        self.custom_collector = collector is not None
        self.sources_file = Path(sources_file or DEFAULT_SOURCES)
        self.collector = collector or self.collect
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.investigation_file = investigation_file
        initialize_database(self.database)

    def collect(self, options, key, now):
        history = read_briefings(self.database, "live", limit=50)
        return collect_sources(options, key, now, self.sources_file, previous_briefings=history, env_file=self.env_file)

    def latest(self, mode):
        saved = read_briefings(self.database, mode, limit=1)
        briefing = saved[0] if saved else None
        attempts = read_refreshes(self.database, mode)
        last_attempt = attempts[0] if attempts else None
        if last_attempt and last_attempt["status"] == "running" and parse_date(last_attempt["lease_until"]) <= self.clock():
            last_attempt = {**last_attempt, "status": "interrupted", "error": "Previous refresh did not finish"}
        last_success = briefing["as_of"] if briefing else None
        stale = last_success is not None and (self.clock() - parse_date(last_success)).total_seconds() > 6 * 3600
        state = "empty" if briefing is None else "stale" if stale else "ready"
        return dict(briefing=briefing, status=dict(state=state, data_mode=mode, stale=stale,
                    last_successful_refresh=last_success, last_attempt=last_attempt,
                    empty_reason="no_saved_briefing" if briefing is None else "no_eligible_stories" if not briefing["stories"] else None))

    def story(self, story_id, mode, briefing_id=None):
        briefings = read_briefings(self.database, mode, limit=1, briefing_id=briefing_id)
        if not briefings:
            return None
        briefing = briefings[0]
        candidate = next((story for story in briefing["candidates"] if story["id"] == story_id), None)
        if candidate is None:
            return None
        run = read_run(self.database, briefing.get("processing_run_id"))
        articles = []
        if run:
            from scripts.validate_gdelt import canonical_url
            urls = {canonical_url(url) for url in candidate["evidence_urls"]}
            articles = [article for article in run["articles"] if article["canonical_url"] in urls]
        return dict(story=candidate, articles=articles, briefing_id=briefing["briefing_id"],
                    data_mode=mode, experimental=briefing["experimental"])

    def refresh(self, mode, days, max_requests):
        now = self.clock().replace(microsecond=0)
        try:
            reserved_requests = 0
            if mode == "live":
                feed_count = 0 if self.custom_collector else len(load_sources(self.sources_file))
                reserved_requests = max_requests + feed_count
                if not self.custom_collector:
                    try:
                        free_key = load_free_news_key(self.env_file)
                    except SourceError:
                        free_key = None
                    if free_key:
                        free_settings = load_free_news_settings()
                        reserved_requests += free_settings["max_requests"] + free_settings["corroboration_requests"]
        except (ValueError, OSError):
            raise RefreshError(503, "Source configuration is invalid. The previous briefing is unchanged.") from None
        job = start_refresh(self.database, mode, now, reserved_requests, max_seconds=120)
        if "error" in job:
            raise RefreshError(job["status_code"], job["error"], job["retry_after"])
        used, api_key = 0, None
        try:
            settings = RankingSettings(**json.loads(self.settings_file.read_text()))
            settings.validate()
            if mode == "sample":
                report = sample_report(now, days)
            else:
                try:
                    api_key = load_api_key(self.env_file)
                except SourceError:
                    if self.custom_collector:
                        raise RefreshError(503, "Configure GNEWS_API_KEY on the server before a live refresh. Sample mode is available explicitly.") from None
                options = Namespace(days=days, query="NBA", max_requests=max_requests, max_seconds=90, timeout=30,
                                    minimum_publishers=settings.minimum_publishers, publisher_aliases=settings.publisher_aliases)
                try:
                    report = self.collector(options, api_key, now)
                except SourceError:
                    used = reserved_requests
                    raise RefreshError(502, "The news source failed. Any previous briefing is still available.") from None
                used = len(report["attempts"])
                if any(attempt["status"] == "failed" for attempt in report["attempts"]) and not report["articles"]:
                    raise RefreshError(502, "The news source failed. Any previous briefing is still available.")
                if any(attempt["status"] == "failed" for attempt in report["attempts"]):
                    report["complete_available_results"] = False
            expected_sources = {"Sample"} if mode == "sample" else {"GNews" if self.custom_collector else "Monitored sources"}
            if report.get("mode") != mode or report.get("provider") not in expected_sources:
                raise RefreshError(502, "The source returned an unexpected data mode. The previous briefing is unchanged.")
            result = process_report(report)
            briefing = rank_stories(result, settings)
            previous = read_briefings(self.database, mode, limit=3)
            briefing = add_investigations(result, briefing, previous, self.investigation_file, self.env_file)
            briefing["source_errors"] = [attempt["error"] for attempt in report["attempts"] if attempt["status"] == "failed"]
            if api_key:
                briefing["source_errors"] = [error.replace(api_key, "[REDACTED]") for error in briefing["source_errors"]]
            run_id = save_run(result, self.database)
            briefing["processing_run_id"] = run_id
            briefing_id = save_briefing(briefing, self.database)
            status = "complete" if report["complete_available_results"] else "partial"
            finish_refresh(self.database, job["id"], self.clock(), status, used, briefing_id)
        except RefreshError as error:
            finish_refresh(self.database, job["id"], self.clock(), "failed", used, error=str(error))
            raise
        except Exception:
            finish_refresh(self.database, job["id"], self.clock(), "failed", max(used, reserved_requests),
                           error="Refresh could not finish. Any previous briefing is still available.")
            raise RefreshError(500, "Refresh could not finish. Any previous briefing is still available.") from None
        return dict(refresh=read_refreshes(self.database, mode)[0], **self.latest(mode))
