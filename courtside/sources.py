"""Combine API discovery and reviewed feeds without counting duplicate URLs twice."""
from argparse import Namespace
from datetime import timedelta
from pathlib import Path
import time

from scripts.validate_gnews import collect_articles, SourceError
from scripts.validate_gdelt import canonical_url, format_time
from .feeds import collect_feeds, load_sources
from .stories import inspect_article, group_articles, parse_date

DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "config/sources.json"


def corroboration_query(articles, available_end):
    candidates = []
    for article in merge_articles(articles):
        if parse_date(article["published_at"]) > available_end:
            continue
        decision, _, features = inspect_article(article)
        if decision == "included" and features["event"] == "game":
            candidates.append({**article, "canonical_url": canonical_url(article["url"]), "features": features})
    groups = group_articles(candidates)
    for group in sorted(groups, key=lambda story: story["latest_published_at"], reverse=True):
        if group["reporting_groups"] != 1:
            continue
        article = next(article for article in candidates if article["canonical_url"] in group["article_urls"])
        return " ".join(team.rsplit(" ", 1)[-1] for team in article["features"]["teams"])
    return None


def merge_articles(articles):
    merged = {}
    for article in articles:
        url = canonical_url(article["url"])
        sources = article.get("collection_sources", ["gnews"])
        if url not in merged:
            merged[url] = {**article, "collection_sources": list(sources)}
            continue
        previous = merged[url]
        combined_sources = sorted(set(previous["collection_sources"]) | set(sources))
        if article.get("investigation_allowed") is False:
            merged[url] = {**article, "collection_sources": combined_sources}
        else:
            previous["collection_sources"] = combined_sources
    return list(merged.values())


def collect_sources(args, api_key, now, sources_file=DEFAULT_SOURCES, feed_transport=None,
                    news_transport=None, clock=time.monotonic, sleep=time.sleep):
    feed_ids = load_sources(sources_file)
    deadline = clock() + args.max_seconds
    start = now - timedelta(days=args.days)
    feed_options = dict(max_seconds=min(25, args.max_seconds / 3), clock=clock)
    if feed_transport is not None:
        feed_options["transport"] = feed_transport
    feed_articles, statuses, attempts = collect_feeds(feed_ids, start, now, **feed_options)
    articles = list(feed_articles)
    news_status = dict(id="gnews", name="GNews", kind="api", status="unconfigured", article_count=0,
                       collected_at=None, delay_hours=12, complete_window=False,
                       note="The free plan excludes the latest 12 hours.")
    statuses.insert(0, news_status)
    remaining = deadline - clock()
    if api_key and remaining > 1:
        discovery_budget = max(1, args.max_requests - 1)
        options = Namespace(**{**vars(args), "max_seconds": remaining, "max_requests": discovery_budget})
        kwargs = dict(clock=clock, sleep=sleep)
        if news_transport is not None:
            kwargs["transport"] = news_transport
        try:
            report = collect_articles(options, api_key, now, **kwargs)
            for attempt in report["attempts"]:
                attempt.update(purpose="discovery", query=args.query)
            query = None
            if args.max_requests > discovery_budget and not any(attempt["status"] == "failed" for attempt in report["attempts"]):
                query = corroboration_query(articles + report["articles"], now - timedelta(hours=12))
            if query and deadline - clock() > 3:
                sleep(2)
                remaining = deadline - clock()
                if remaining > 1:
                    focused_options = Namespace(**{**vars(args), "query": query, "max_requests": 1, "max_seconds": remaining})
                    focused = collect_articles(focused_options, api_key, now, **kwargs)
                    report["articles"] = merge_articles(report["articles"] + focused["articles"])
                    report["attempts"].extend({**attempt, "purpose": "corroboration", "query": query} for attempt in focused["attempts"])
                    report["complete_available_results"] = False
                    report["stop_reason"] = "Discovery and one targeted corroboration search provide partial coverage"
            articles.extend(report["articles"])
            attempts.extend({**attempt, "source": "gnews"} for attempt in report["attempts"])
            failures = [attempt for attempt in report["attempts"] if attempt["status"] == "failed"]
            news_status.update(status="failed" if failures and not report["articles"] else "partial" if not report["complete_available_results"] else "ok",
                article_count=len(report["articles"]), collected_at=report["generated_at"] if any(a["status"] == "ok" for a in report["attempts"]) else None,
                complete_window=report["complete_available_results"], note=report["stop_reason"],
                available_end=report["searchable_end"])
            if failures:
                news_status["error"] = "GNews could not complete collection"
        except SourceError:
            attempts.append(dict(source="gnews", status="failed", error="GNews unavailable"))
            news_status.update(status="failed", error="GNews unavailable")
    elif api_key:
        news_status.update(status="skipped", note="Collection time budget exhausted")
    else:
        news_status["note"] = "No GNews key configured. Only enabled feeds were requested."
    usable = any(status["status"] in {"ok", "partial"} for status in statuses)
    if not usable:
        raise SourceError("No configured source completed a request. The previous briefing is unchanged.")
    available_end = max(status["available_end"] for status in statuses if status.get("available_end") and status["status"] in {"ok", "partial"})
    return dict(provider="Monitored sources", mode="live", generated_at=format_time(now),
                requested_start=format_time(start), requested_end=format_time(now), searchable_end=available_end,
                freshness_delay_hours=0, complete_available_results=False,
                stop_reason="Feed snapshots and bounded API results are partial coverage",
                articles=merge_articles(articles), sources=statuses, attempts=attempts)
