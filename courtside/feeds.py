from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from scripts.validate_gnews import SourceError
from scripts.validate_gdelt import canonical_url, format_time

CATALOG = {
    "yahoo-nba": ("Yahoo Sports", "https://sports.yahoo.com/nba/rss/", "display_only"),
    "espn-nba": ("ESPN", "https://www.espn.com/espn/rss/nba/news", "pending"),
    "cbs-nba": ("CBS Sports", "https://www.cbssports.com/rss/headlines/nba/", "pending"),
    "hoops-rumors": ("Hoops Rumors", "https://www.hoopsrumors.com/feed", "pending"),
    "realgm": ("RealGM", "https://basketball.realgm.com/rss/wiretap/0/0.xml", "pending"),
    "athletic-nba": ("The Athletic", "https://www.nytimes.com/athletic/rss/nba/", "pending"),
    "guardian-nba": ("The Guardian", "https://www.theguardian.com/sport/nba/rss", "pending"),
    "post-nba": ("New York Post", "https://nypost.com/nba/feed/", "pending"),
    "hoops-wire": ("Hoops Wire", "https://hoopswire.com/feed/", "pending"),
    "basketball-insiders": ("Basketball Insiders", "https://www.basketballinsiders.com/feed/", "pending"),
    "bleacher-report": ("Bleacher Report", "https://feeds.bleacherreport.com/articles", "pending"),
}


def load_sources(path):
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict):
        raise ValueError("Source settings must be an object")
    feeds = config.get("feeds")
    if not isinstance(feeds, list) or len(feeds) > len(CATALOG):
        raise ValueError("Expected a list of catalog feeds")
    seen, enabled = set(), []
    for feed in feeds:
        if not isinstance(feed, dict) or set(feed) != {"id", "enabled"}:
            raise ValueError("Each feed needs an id and enabled flag")
        name = feed["id"]
        if not isinstance(name, str) or name not in CATALOG or name in seen or type(feed["enabled"]) is not bool:
            raise ValueError("Invalid or repeated feed configuration")
        seen.add(name)
        if feed["enabled"]:
            if CATALOG[name][2] == "pending":
                raise ValueError(f"{name} still needs a usage review before enabling")
            enabled.append(name)
    if len(enabled) > 4:
        raise ValueError("At most four feeds can run in one refresh")
    return enabled


def fetch_feed(url, timeout):
    try:
        response = subprocess.run(
            ["curl", "--disable", "--silent", "--show-error", "--max-time", str(timeout),
             "--connect-timeout", str(min(timeout, 8)), "--max-filesize", "2000000",
             "--proto", "=https", "--user-agent", "CourtSide/0.1 RSS reader",
             "--write-out", "\n%{http_code}", url], capture_output=True, timeout=timeout + 0.2)
        body, status = response.stdout.rsplit(b"\n", 1)
        if response.returncode or status != b"200":
            raise SourceError("Feed request failed. No retries or redirects were followed")
        return body
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        raise SourceError("Feed unavailable or timed out") from None


def parse_feed(body, feed_id, start, end, collected_at):
    if not isinstance(body, bytes) or len(body) > 2000000 or re.search(br"<!\s*(DOCTYPE|ENTITY)", body, re.I) or b"\x00" in body:
        raise SourceError("Feed XML is unsafe or exceeds the size limit")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise SourceError("Feed did not contain valid XML") from None
    if root.tag != "rss" or root.find("channel") is None:
        raise SourceError("Expected an RSS channel")
    items = root.findall("./channel/item")
    if len(items) > 1000:
        raise SourceError("Feed exceeds the item limit")
    publisher, feed_url, policy = CATALOG[feed_id]
    articles, rejected, outside = [], 0, 0
    for item in items:
        try:
            title = unescape(item.findtext("title", ""))
            url = item.findtext("link", "").strip()
            published = parsedate_to_datetime(item.findtext("pubDate", "").strip())
            if published.tzinfo is None or not title.strip() or len(title) > 2000:
                raise ValueError("Missing dated headline")
            canonical = canonical_url(url)
            if urlsplit(canonical).hostname != urlsplit(canonical_url(feed_url)).hostname:
                raise ValueError("Unexpected article host")
            if not start <= published <= end:
                outside += 1
                continue
            articles.append(dict(title=title, url=url, canonical_url=canonical,
                publisher_name=publisher, publisher_host=urlsplit(canonical).hostname,
                source_url=feed_url, published_at=format_time(published.astimezone(timezone.utc)),
                publication_date_basis="RSS supplied, not independently verified", collected_at=collected_at,
                description=None, content_excerpt=None, collection_sources=[feed_id],
                material_policy=policy, investigation_allowed=False,
                attribution_note="Feed publisher label. Original reporting and syndication are not verified."))
        except (TypeError, ValueError, OverflowError):
            rejected += 1
    return dict(articles=articles, rejected_records=rejected, outside_window=outside, items=len(items))


def collect_feeds(feed_ids, start, end, transport=fetch_feed, max_seconds=25, clock=time.monotonic):
    deadline = clock() + max_seconds
    articles, statuses, attempts = [], [], []
    for feed_id in feed_ids:
        publisher, url, policy = CATALOG[feed_id]
        status = dict(id=feed_id, name=publisher, kind="rss", material_policy=policy,
                      status="skipped", collected_at=None, article_count=0, complete_window=False,
                      note="A feed is a recent snapshot and may not cover the full requested period.")
        statuses.append(status)
        remaining = deadline - clock()
        if remaining <= 0.5:
            status["error"] = "Feed time budget exhausted"
            continue
        attempt = dict(source=feed_id, status="failed")
        attempts.append(attempt)
        try:
            body = transport(url, min(12, remaining - 0.2))
            collected_at = format_time(datetime.now(timezone.utc))
            parsed = parse_feed(body, feed_id, start, end, collected_at)
            articles.extend(parsed["articles"])
            status.update(status="ok", collected_at=collected_at, article_count=len(parsed["articles"]),
                          rejected_records=parsed["rejected_records"], outside_window=parsed["outside_window"],
                          items=parsed["items"], available_end=format_time(end))
            attempt.update(status="ok", count=len(parsed["articles"]))
        except SourceError as error:
            status.update(status="failed", error=str(error))
            attempt["error"] = str(error)
    return articles, statuses, attempts
