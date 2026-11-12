from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit

try:
    from .validate_gdelt import UTC, SourceError, canonical_url, format_time, normalize_title, classify_title
except ImportError:
    from validate_gdelt import UTC, SourceError, canonical_url, format_time, normalize_title, classify_title

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://gnews.io/api/v4/search"


def load_api_key(path=PROJECT_ROOT / ".env"):
    api_key = os.environ.get("GNEWS_API_KEY", "").strip()
    if not api_key and path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name.strip() == "GNEWS_API_KEY":
                api_key = value.strip().strip("\"'")
                break
    if not api_key or api_key.lower() in {"your_actual_key", "your_api_key", "your_api_key_here"}:
        raise SourceError("Set GNEWS_API_KEY in the repository's .env file before running.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", api_key):
        raise SourceError("GNEWS_API_KEY contains unsupported characters. Check the local .env entry.")
    return api_key


def fetch_page(url, api_key, timeout):
    try:
        response = subprocess.run(
            ["curl", "--disable", "--silent", "--show-error", "--max-time", str(timeout),
             "--connect-timeout", str(min(timeout, 25)), "--max-filesize", "2000000",
             "--header", "@-", "--write-out", "\n%{http_code}", url],
            input=f"X-Api-Key: {api_key}\n", capture_output=True, text=True, timeout=timeout + 0.2)
    except FileNotFoundError:
        raise SourceError("curl is required but not installed") from None
    except subprocess.TimeoutExpired:
        raise SourceError("GNews request timed out") from None
    if response.returncode:
        raise SourceError(f"GNews connection failed with curl exit code {response.returncode}")
    try:
        body, status = response.stdout.rsplit("\n", 1)
        status = int(status)
    except ValueError:
        raise SourceError("Could not read the HTTP status from curl") from None
    errors = {400: "Invalid GNews request or malformed key", 401: "GNews rejected the API key",
              403: "GNews denied access. Check email verification and plan permissions",
              429: "GNews rate or quota limit reached. No automatic retries were made"}
    if status != 200:
        raise SourceError(errors.get(status, f"GNews HTTP {status}"))
    try:
        response_data = json.loads(body)
    except ValueError:
        raise SourceError("GNews returned non-JSON data") from None
    if (not isinstance(response_data, dict) or not isinstance(response_data.get("articles"), list) or
            type(response_data.get("totalArticles")) is not int or response_data["totalArticles"] < 0):
        raise SourceError("GNews response is missing a valid articles array or totalArticles count")
    return response_data


def parse_article(raw_article, start, end, collected_at):
    if not isinstance(raw_article, dict):
        raise ValueError("article is not an object")
    title, url, published = raw_article.get("title"), raw_article.get("url"), raw_article.get("publishedAt")
    source = raw_article.get("source")
    if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
        raise ValueError("missing title or URL")
    if not isinstance(source, dict) or not isinstance(source.get("name"), str) or not source["name"].strip():
        raise ValueError("missing publisher name")
    if not isinstance(published, str):
        raise ValueError("missing publication timestamp")
    published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
    if published_at.tzinfo is None or not start <= published_at <= end:
        raise ValueError("publication timestamp outside requested window or missing time zone")
    canonical = canonical_url(url)
    relevance, reason = classify_title(title)
    return dict(title=title.strip(), url=url, canonical_url=canonical,
                publisher_name=source["name"].strip(), publisher_host=urlsplit(canonical).hostname,
                source_url=source.get("url"), published_at=format_time(published_at),
                publication_date_basis="GNews supplied, not independently verified",
                collected_at=collected_at, description=raw_article.get("description"),
                content_excerpt=raw_article.get("content"), relevance=relevance, relevance_reason=reason)


def collect_articles(args, api_key, now, transport=fetch_page, clock=time.monotonic, sleep=time.sleep):
    start, end = now - timedelta(days=args.days), now - timedelta(hours=12)
    deadline = clock() + args.max_seconds
    attempts, articles, rejected, notices = [], {}, [], []
    retrieved_count = duplicate_urls = 0
    window_count = min(args.days, args.max_requests)
    boundaries = [start + (end - start) * index / window_count for index in range(window_count + 1)]
    boundaries = [value.replace(microsecond=0) for value in boundaries]
    windows = [dict(start=format_time(boundaries[index]),
                    end=format_time(boundaries[index + 1] if index == window_count - 1 else boundaries[index + 1] - timedelta(microseconds=1)),
                    next_page=1, retrieved_rows=0, reported_total=None, complete=False, stopped=False)
               for index in reversed(range(window_count))]
    stop_reason = "request limit reached"
    for request_number in range(args.max_requests):
        available = [window for window in windows if not window["complete"] and not window["stopped"]]
        if not available:
            stop_reason = "all reported matches downloaded" if all(w["complete"] for w in windows) else "Some windows returned incomplete results"
            break
        window = min(available, key=lambda item: item["next_page"])
        if request_number:
            if deadline - clock() <= 3:
                stop_reason = "time limit reached"
                break
            sleep(2)
        remaining = deadline - clock()
        if remaining <= 0.5:
            stop_reason = "time limit reached"
            break
        page = window["next_page"]
        url = ENDPOINT + "?" + urlencode(dict(q=args.query, lang="en", max=10, page=page,
                                                sortby="publishedAt", nullable="description,content,image",
                                                truncate="content", **{"from": window["start"], "to": window["end"]}))
        attempt = dict(page=page, url=url, window_start=window["start"], window_end=window["end"])
        attempts.append(attempt)
        print(f"GNews request {request_number + 1}/{args.max_requests}: {window['start']} to {window['end']}, page {page}", flush=True)
        try:
            response_data = transport(url, api_key, min(args.timeout, remaining - 0.3))
        except SourceError as error:
            attempt.update(status="failed", error=str(error))
            stop_reason = str(error)
            break
        rows = response_data["articles"]
        window["reported_total"] = response_data["totalArticles"]
        window["retrieved_rows"] += len(rows)
        window["next_page"] += 1
        retrieved_count += len(rows)
        attempt.update(status="ok", count=len(rows), total_articles=window["reported_total"])
        notices.append({k: response_data[k] for k in ("information", "articlesRemovedFromResponse") if k in response_data})
        for raw_article in rows:
            try:
                article = parse_article(raw_article, datetime.fromisoformat(window["start"].replace("Z", "+00:00")),
                                        datetime.fromisoformat(window["end"].replace("Z", "+00:00")),
                                        format_time(datetime.now(UTC)))
                canonical = article["canonical_url"]
                if canonical in articles:
                    duplicate_urls += 1
                else:
                    articles[canonical] = article
            except (ValueError, TypeError) as error:
                rejected.append(dict(reason=str(error), window_start=window["start"], window_end=window["end"]))
        window["complete"] = window["retrieved_rows"] >= window["reported_total"]
        if not window["complete"] and (len(rows) < 10 or window["retrieved_rows"] >= 1000):
            window["stopped"] = True
    all_pages_fetched = all(window["complete"] for window in windows)
    if all_pages_fetched:
        stop_reason = "all reported matches downloaded"
    total_articles = sum(window["reported_total"] for window in windows) if all(window["reported_total"] is not None for window in windows) else None
    saved_articles = list(articles.values())
    groups = defaultdict(list)
    for article in saved_articles:
        groups[normalize_title(article["title"])].append(article["url"])
    complete = all_pages_fetched and not rejected and not duplicate_urls
    return dict(provider="GNews", mode="live", query=args.query, generated_at=format_time(now),
                requested_start=format_time(start), requested_end=format_time(now), searchable_end=format_time(end),
                freshness_delay_hours=12, complete_available_results=complete, stop_reason=stop_reason,
                max_requests=args.max_requests, max_seconds=args.max_seconds,
                collection_strategy="balanced time windows, then round-robin pagination", windows=windows,
                attempts=attempts, provider_notices=notices, rejected_records=rejected,
                articles=saved_articles, possible_duplicate_titles=[dict(title=k, urls=v) for k, v in groups.items() if len(v) > 1],
                summary=dict(retrieved_rows=retrieved_count, unique_urls=len(saved_articles), reported_total=total_articles,
                             duplicate_url_observations=duplicate_urls,
                             publishers=dict(Counter(a["publisher_name"] for a in saved_articles)),
                             published_utc_days=dict(Counter(a["published_at"][:10] for a in saved_articles)),
                             relevance=dict(Counter(a["relevance"] for a in saved_articles))))


def save_report(report, output, api_key):
    def redact(value):
        if isinstance(value, str):
            return value.replace(api_key, "[REDACTED]")
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, dict):
            return {name: redact(item) for name, item in value.items()}
        return value
    report = redact(report)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = report["summary"]
    lines = ["# Courtside-Agent GNews results", "", "Data source: live API", "",
             f"Requested: {report['requested_start']} to {report['requested_end']}",
             f"Searchable through: {report['searchable_end']} (free-plan 12-hour delay)",
             f"Collection: {'All available matches downloaded' if report['complete_available_results'] else 'Incomplete'}",
             f"Stop reason: {report['stop_reason']}",
             f"Retrieved rows: {summary['retrieved_rows']}, unique URLs: {summary['unique_urls']}, reported total: {summary['reported_total']}",
             f"Possible duplicate headline groups: {len(report['possible_duplicate_titles'])}",
             f"Publishers reported by GNews: {summary['publishers']}", f"Title checks: {summary['relevance']}", "",
             "Publisher labels and dates are supplied by GNews. Independent reporting and",
             "publication dates are not verified. These are discovery results, not ranked",
             "stories. The latest 12 hours are unavailable on the free plan.", "", "## Review sample", ""]
    window_lines = ["## Collection windows", "", "Each window gets a first page before another window gets more pages.", "",
                    "| From | Through | Requests | Rows | Reported matches | Complete |",
                    "| --- | --- | --- | ---: | ---: | --- |"]
    for window in report.get("windows", []):
        requests = sum(attempt.get("window_start") == window["start"] for attempt in report["attempts"])
        window_lines.append(f"| {window['start']} | {window['end']} | {requests} | {window['retrieved_rows']} | {window['reported_total']} | {window['complete']} |")
    if report.get("windows"):
        lines[-2:-2] = window_lines + [""]
    lines += [f"- {a['relevance']}: {a['title']} ({a['publisher_name']}) {a['url']}" for a in report["articles"][:10]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    fields = ["title", "url", "canonical_url", "publisher_name", "publisher_host", "source_url",
              "published_at", "publication_date_basis", "collected_at", "description", "content_excerpt", "relevance", "relevance_reason"]
    with (output / "articles.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for article in report["articles"]:
            writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in article.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 8), default=3)
    parser.add_argument("--query", default="NBA")
    parser.add_argument("--max-requests", type=int, default=3)
    parser.add_argument("--max-seconds", type=float, default=90)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts/gnews-validation")
    args = parser.parse_args()
    if not (1 <= args.max_requests <= 100 and 1 <= args.max_seconds <= 600 and
            1 <= args.timeout <= 60 and 1 <= len(args.query.strip()) <= 200):
        parser.error("Use 1 to 100 requests, 1 to 600 total seconds, 1 to 60 seconds per request, and a query up to 200 characters")
    try:
        api_key = load_api_key()
    except SourceError as error:
        print(str(error), file=sys.stderr)
        return 2
    report = collect_articles(args, api_key, datetime.now(UTC).replace(microsecond=0))
    save_report(report, args.output, api_key)
    print(f"Retrieved {report['summary']['unique_urls']} unique articles. {report['stop_reason']}.")
    print(f"Report: {args.output / 'report.md'}")
    return 0 if report["complete_available_results"] else 2


if __name__ == "__main__":
    sys.exit(main())
