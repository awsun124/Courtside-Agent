"""Combine API discovery and reviewed feeds without counting duplicate URLs twice."""
from argparse import Namespace
from datetime import timedelta
from pathlib import Path
import time
from urllib.parse import urlsplit

from scripts.validate_gnews import collect_articles, SourceError
from scripts.validate_gdelt import canonical_url, format_time
from .feeds import collect_feeds, load_sources
from .stories import inspect_article, group_articles, parse_date, clean_text
from .ranking import reporting_groups

DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "config/sources.json"


def story_candidates(articles, available_end, publisher_aliases=None):
    candidates = []
    for article in merge_articles(articles):
        if parse_date(article["published_at"]) > available_end:
            continue
        decision, _, features = inspect_article(article)
        if decision == "included" and features["event"] in {"game", "injury"}:
            candidates.append({**article, "canonical_url": canonical_url(article["url"]), "features": features})
    aliases = publisher_aliases or {}
    for article in candidates:
        domain = urlsplit(article["canonical_url"]).hostname
        article.update(publisher_host=domain, publisher_id=clean_text(aliases.get(domain, article["publisher_name"])))
    groups = group_articles(candidates)
    for group in groups:
        members = [article for article in candidates if article["canonical_url"] in group["article_urls"]]
        group["reporting_groups"] = len(reporting_groups(members))
        group["query"] = None
        for article in sorted(members, key=lambda item: parse_date(item["published_at"]), reverse=True):
            features = article["features"]
            if features["event"] == "game":
                group["query"] = " ".join(team.rsplit(" ", 1)[-1] for team in features["teams"])
            elif len(features["subjects"]) == 1 and len(features["body_parts"]) == 1:
                group["query"] = " ".join([features["subjects"][0], features["body_parts"][0], "injury"])
            if group["query"]:
                break
    return groups


def plan_searches(articles, available_end, now, previous_briefings=(), minimum_publishers=2, publisher_aliases=None):
    recent, seen_queries = {}, set()
    for briefing in sorted(previous_briefings, key=lambda item: parse_date(item["as_of"]), reverse=True):
        if briefing.get("data_mode", "live") != "live":
            continue
        age = (now - parse_date(briefing["as_of"])).total_seconds() / 3600
        if not 0 <= age < 6:
            continue
        for entry in briefing.get("collection_activity", []):
            if entry.get("purpose") != "corroboration" or not entry.get("requests") or not entry.get("query"):
                continue
            query_key = clean_text(entry["query"])
            if query_key in seen_queries:
                continue
            seen_queries.add(query_key)
            gain = entry.get("reporting_groups_added", entry.get("added_articles", 0))
            wait = 6 if entry.get("status") == "failed" or gain == 0 else 1
            if age < wait:
                recent[query_key] = "Recent search added no reporting groups or failed. Waiting up to six hours." if wait == 6 else "This story was searched within the last hour. Trying other candidates first."
    planned, seen = [], set()
    groups = story_candidates(articles, available_end, publisher_aliases)
    groups.sort(key=lambda group: (-group["reporting_groups"], -parse_date(group["latest_published_at"]).timestamp(), group["id"]))
    for group in groups:
        query = group["query"]
        if not query or group["reporting_groups"] >= minimum_publishers or query in seen:
            continue
        seen.add(query)
        planned.append({**group, "skip_reason": recent.get(clean_text(query))})
    return planned


def corroboration_query(articles, available_end):
    planned = plan_searches(articles, available_end, available_end + timedelta(hours=12))
    return planned[0]["query"] if planned else None


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
                    news_transport=None, clock=time.monotonic, sleep=time.sleep, previous_briefings=()):
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
        discovery_budget = max(1, args.max_requests - 2)
        options = Namespace(**{**vars(args), "max_seconds": remaining, "max_requests": discovery_budget})
        kwargs = dict(clock=clock, sleep=sleep)
        if news_transport is not None:
            kwargs["transport"] = news_transport
        try:
            report = collect_articles(options, api_key, now, **kwargs)
            activity.append(search_activity(report, articles, "discovery", args.query))
            for attempt in report["attempts"]:
                attempt.update(purpose="discovery", query=args.query)
            target_note = "The request budget allows discovery only."
            attempted_queries, logged_skips = set(), set()
            for _ in range(args.max_requests - discovery_budget):
                if any(attempt["status"] == "failed" for attempt in report["attempts"]):
                    target_note = "A search failed, so remaining targeted searches were skipped."
                    break
                planned = plan_searches(articles + report["articles"], now - timedelta(hours=12), now,
                    previous_briefings, getattr(args, "minimum_publishers", 2), getattr(args, "publisher_aliases", None))
                for candidate in planned:
                    if candidate["skip_reason"] and candidate["query"] not in logged_skips and len(logged_skips) < 5:
                        activity.append(collection_activity("gnews", "GNews", "corroboration", [], [], [], "skipped",
                            candidate["query"], candidate["skip_reason"]))
                        logged_skips.add(candidate["query"])
                candidate = next((item for item in planned if not item["skip_reason"] and item["query"] not in attempted_queries), None)
                if candidate is None:
                    target_note = "No additional eligible candidate was available outside the recent-search cooldowns."
                    break
                query = candidate["query"]
                if deadline - clock() <= 3:
                    target_note = "Collection time budget exhausted."
                    break
                sleep(2)
                remaining = deadline - clock()
                if remaining <= 1:
                    target_note = "Collection time budget exhausted."
                    break
                if remaining > 1:
                    attempted_queries.add(query)
                    focused_options = Namespace(**{**vars(args), "query": query, "max_requests": 1, "max_seconds": remaining})
                    focused = collect_articles(focused_options, api_key, now, **kwargs)
                    entry = search_activity(focused, articles + report["articles"], "corroboration", query)
                    updated = story_candidates(articles + report["articles"] + focused["articles"], now - timedelta(hours=12), getattr(args, "publisher_aliases", None))
                    matches = [group for group in updated if set(group["article_urls"]) & set(candidate["article_urls"])]
                    entry["reporting_groups_added"] = max(0, max((group["reporting_groups"] for group in matches), default=0) - candidate["reporting_groups"])
                    entry["selection_reason"] = f"Needs {getattr(args, 'minimum_publishers', 2)} reporting groups, found {candidate['reporting_groups']}."
                    activity.append(entry)
                    report["articles"] = merge_articles(report["articles"] + focused["articles"])
                    report["attempts"].extend({**attempt, "purpose": "corroboration", "query": query} for attempt in focused["attempts"])
                    report["complete_available_results"] = False
                    report["stop_reason"] = "Discovery and targeted corroboration searches provide partial coverage"
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
