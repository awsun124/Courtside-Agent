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
        if decision == "included" and features["event"] in {"game", "injury"}:
            candidates.append({**article, "canonical_url": canonical_url(article["url"]), "features": features})
    groups = group_articles(candidates)
    for group in sorted(groups, key=lambda story: story["latest_published_at"], reverse=True):
        if group["reporting_groups"] != 1:
            continue
        article = next(article for article in candidates if article["canonical_url"] in group["article_urls"])
        features = article["features"]
        if features["event"] == "game":
            return " ".join(team.rsplit(" ", 1)[-1] for team in features["teams"])
        for article in sorted(candidates, key=lambda item: item["published_at"], reverse=True):
            if article["canonical_url"] not in group["article_urls"]:
                continue
            features = article["features"]
            if len(features["subjects"]) == 1 and len(features["body_parts"]) == 1:
                return " ".join([features["subjects"][0], features["body_parts"][0], "injury"])
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


def collection_activity(source_id, source_name, purpose, records, previous, attempts, status, query=None, note=None):
    previous_urls = {canonical_url(article["url"]) for article in previous}
    current_urls = {canonical_url(article["url"]) for article in records}
    previous_publishers = {article["publisher_name"] for article in previous}
    publishers = {article["publisher_name"] for article in records}
    return dict(source_id=source_id, source_name=source_name, purpose=purpose, query=query,
                status=status, requests=len(attempts), returned_results=sum(attempt.get("count", 0) for attempt in attempts),
                added_articles=len(current_urls - previous_urls), publisher_labels=len(publishers),
                added_publisher_labels=len(publishers - previous_publishers), note=note)


def search_activity(report, previous, purpose, query):
    attempts = report["attempts"]
    failed = any(attempt["status"] == "failed" for attempt in attempts)
    succeeded = any(attempt["status"] == "ok" for attempt in attempts)
    status = "failed" if failed and not succeeded else "partial" if failed or not report["complete_available_results"] else "ok"
    note = "Some matches were not downloaded." if status == "partial" else None
    if failed:
        limited = any("rate or quota" in attempt.get("error", "").lower() for attempt in attempts)
        note = "Rate or quota limit reached. No retry was made." if limited else "The search could not finish. No retry was made."
    entry = collection_activity("gnews", "GNews", purpose, report["articles"], previous, attempts, status, query, note)
    entry.update(window_start=report["requested_start"], window_end=report["searchable_end"])
    if purpose == "corroboration":
        entry["topic"] = "injury" if query.endswith(" injury") else "game"
    return entry


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
    activity, previous_feed_articles = [], []
    for source in statuses:
        records = [article for article in feed_articles if source["id"] in article.get("collection_sources", [])]
        source_attempts = [attempt for attempt in attempts if attempt["source"] == source["id"]]
        note = "Feed snapshot only. This may not cover the full window."
        if source["status"] == "failed":
            note = "Feed request failed."
        elif source["status"] == "skipped":
            note = "Feed time budget exhausted."
        activity.append(collection_activity(source["id"], source["name"], "feed", records, previous_feed_articles,
                                            source_attempts, source["status"], note=note))
        previous_feed_articles.extend(records)
    news_status = dict(id="gnews", name="GNews", kind="api", status="unconfigured", article_count=0,
                       collected_at=None, delay_hours=12, complete_window=False,
                       note="The free plan excludes the latest 12 hours.")
    statuses.insert(0, news_status)
    remaining = deadline - clock()
    target_note = "GNews is not configured." if not api_key else "Collection time budget exhausted."
    if api_key and remaining > 1:
        discovery_budget = max(1, args.max_requests - 1)
        options = Namespace(**{**vars(args), "max_seconds": remaining, "max_requests": discovery_budget})
        kwargs = dict(clock=clock, sleep=sleep)
        if news_transport is not None:
            kwargs["transport"] = news_transport
        try:
            report = collect_articles(options, api_key, now, **kwargs)
            activity.append(search_activity(report, articles, "discovery", args.query))
            for attempt in report["attempts"]:
                attempt.update(purpose="discovery", query=args.query)
            query = None
            target_note = "The request budget allows discovery only."
            if args.max_requests > discovery_budget and not any(attempt["status"] == "failed" for attempt in report["attempts"]):
                query = corroboration_query(articles + report["articles"], now - timedelta(hours=12))
                target_note = "No eligible game or specific injury candidate was available before the source delay cutoff." if not query else "Collection time budget exhausted."
            elif any(attempt["status"] == "failed" for attempt in report["attempts"]):
                target_note = "Discovery failed, so the targeted search was skipped."
            if query and deadline - clock() > 3:
                sleep(2)
                remaining = deadline - clock()
                if remaining > 1:
                    focused_options = Namespace(**{**vars(args), "query": query, "max_requests": 1, "max_seconds": remaining})
                    focused = collect_articles(focused_options, api_key, now, **kwargs)
                    activity.append(search_activity(focused, articles + report["articles"], "corroboration", query))
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
            target_note = "Discovery failed, so the targeted search was skipped."
    elif api_key:
        news_status.update(status="skipped", note="Collection time budget exhausted")
    else:
        news_status["note"] = "No GNews key configured. Only enabled feeds were requested."
    if not any(entry["purpose"] == "discovery" for entry in activity):
        activity.append(collection_activity("gnews", "GNews", "discovery", [], [],
            [attempt for attempt in attempts if attempt.get("source") == "gnews"], news_status["status"], note=news_status.get("note") or "GNews unavailable."))
    if not any(entry["purpose"] == "corroboration" for entry in activity):
        activity.append(collection_activity("gnews", "GNews", "corroboration", [], [], [], "skipped", note=target_note))
    usable = any(status["status"] in {"ok", "partial"} for status in statuses)
    if not usable:
        raise SourceError("No configured source completed a request. The previous briefing is unchanged.")
    available_end = max(status["available_end"] for status in statuses if status.get("available_end") and status["status"] in {"ok", "partial"})
    return dict(provider="Monitored sources", mode="live", generated_at=format_time(now),
                requested_start=format_time(start), requested_end=format_time(now), searchable_end=available_end,
                freshness_delay_hours=0, complete_available_results=False,
                stop_reason="Feed snapshots and bounded API results are partial coverage",
                articles=merge_articles(articles), sources=statuses, attempts=attempts, collection_activity=activity)
