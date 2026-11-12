from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import csv
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UTC = timezone.utc
ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"


def format_time(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_seen_at(value):
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def canonical_url(value):
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        raise ValueError("invalid article URL")
    host = parts.hostname.lower().removeprefix("www.")
    if parts.port:
        host += f":{parts.port}"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", urlencode(sorted(query)), ""))


def normalize_title(title):
    return " ".join(re.findall(r"\w+", html.unescape(title).casefold()))


def classify_title(title):
    text = normalize_title(title)
    if re.search(r"\b(promo code|referral code|best bets|betting promos|sportsbook bonus)\b", text):
        return "excluded", "promotional/betting title"
    if re.search(r"\b(nba|national basketball association|lakers|celtics|knicks|76ers|sixers|"
                 r"mavericks|cavaliers|timberwolves|pelicans|grizzlies|clippers|raptors|"
                 r"trail blazers|brooklyn nets|golden state warriors|oklahoma city thunder|"
                 r"miami heat|chicago bulls|milwaukee bucks|denver nuggets|indiana pacers|houston rockets|"
                 r"detroit pistons|atlanta hawks|charlotte hornets|orlando magic|phoenix suns|"
                 r"sacramento kings|san antonio spurs|utah jazz|washington wizards)\b", text):
        return "candidate", "title mentions the NBA or a team, needs review"
    return "uncertain", "title alone is not enough to tell, needs review"


class SourceError(Exception):
    def __init__(self, message, retryable=False, details=None, cooldown=0):
        super().__init__(message)
        self.retryable = retryable
        self.details = details or {}
        self.cooldown = cooldown


def decode_response(status, body):
    if status == 429 or "please limit requests" in body.lower():
        raise SourceError("GDELT rate limit", retryable=True, cooldown=30)
    if status >= 500:
        raise SourceError(f"GDELT HTTP {status}", retryable=True)
    if status != 200:
        raise SourceError(f"GDELT HTTP {status}")
    try:
        response_data = json.loads(body)
    except ValueError:
        raise SourceError("Non-JSON response: " + body[:180].replace("\n", " ")) from None
    if not isinstance(response_data, dict) or not isinstance(response_data.get("articles"), list):
        raise SourceError("JSON response missing articles array")
    return response_data["articles"]


def fetch(url, timeout, connect_timeout=20):
    try:
        result = subprocess.run(
            ["curl", "--disable", "--silent", "--show-error", "--max-time", str(timeout),
             "--connect-timeout", str(min(connect_timeout, timeout)), "--max-filesize", "10000000",
             "--write-out", "\n%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} %{time_total}", url],
            capture_output=True, text=True, timeout=timeout + 0.2)
    except subprocess.TimeoutExpired:
        raise SourceError("Request timed out", retryable=True) from None
    except FileNotFoundError:
        raise SourceError("curl is required but not installed") from None
    try:
        body, metadata = result.stdout.rsplit("\n", 1)
        status, dns, tcp, tls, total = metadata.split()
        details = dict(http_status=int(status), dns_seconds=float(dns),
                       tcp_seconds=float(tcp), tls_seconds=float(tls), total_seconds=float(total))
    except (ValueError, TypeError):
        raise SourceError(f"curl did not return connection metadata: {result.stderr[:180].strip()}") from None
    if result.returncode:
        phase = "transport"
        if result.returncode == 6:
            phase = "dns"
        elif result.returncode == 28:
            phase = "response" if float(tls) else "tls" if float(tcp) else "connection"
        elif result.returncode == 60:
            phase = "certificate"
        details["failure_phase"] = phase
        raise SourceError(f"{phase} failure: {result.stderr[:180].strip()}",
                          retryable=result.returncode in {5, 6, 7, 18, 28, 52, 56}, details=details)
    try:
        return decode_response(int(status), body)
    except SourceError as error:
        error.details.update(details)
        raise


def split_date_range(start, end, hours):
    while start < end:
        stop = min(end, start + timedelta(hours=hours))
        yield start, stop
        start = stop


def parse_article(raw_article, collected_at, start, end):
    if not isinstance(raw_article, dict):
        raise ValueError("article is not an object")
    url, title = raw_article.get("url"), raw_article.get("title")
    if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
        raise ValueError("missing URL/title")
    canonical = canonical_url(url)
    seen = parse_seen_at(raw_article.get("seendate", ""))
    if not start <= seen <= end:
        raise ValueError("observed timestamp outside response window")
    relevance, reason = classify_title(title)
    return dict(url=url, canonical_url=canonical, title=html.unescape(title).strip(),
                publisher_host=urlsplit(canonical).hostname, publisher_name=None,
                gdelt_domain=raw_article.get("domain"), gdelt_seen_at=format_time(seen),
                published_at=None, collected_at=collected_at,
                language=raw_article.get("language"), source_country=raw_article.get("sourcecountry"),
                relevance=relevance, relevance_reason=reason)


def collect_articles(args, end, transport=None, clock=time.monotonic, sleep=time.sleep):
    connect_timeout = getattr(args, "connect_timeout", 20)
    if transport is None:
        transport = lambda url, timeout: fetch(url, timeout, connect_timeout)
    start = end - timedelta(days=args.days)
    pending = deque(split_date_range(start, end, args.window_hours))
    deadline, last_request = clock() + args.max_seconds, None
    next_request_at = 0
    attempts, intervals, articles, rejected = [], [], {}, []
    duplicate_urls = 0
    while pending:
        window_start, window_end = pending.popleft()
        interval = dict(start=format_time(window_start), end=format_time(window_end), status="unattempted")
        intervals.append(interval)
        query_params = dict(query=args.query, mode="artlist", format="json", sort="datedesc",
                      maxrecords=args.max_records, startdatetime=window_start.strftime("%Y%m%d%H%M%S"),
                      enddatetime=window_end.strftime("%Y%m%d%H%M%S"))
        url = ENDPOINT + "?" + urlencode(query_params)
        for retry in range(args.retries + 1):
            delay = 0 if last_request is None else max(0, last_request + args.interval * (2 ** retry) - clock())
            delay = max(delay, next_request_at - clock())
            if len(attempts) >= args.max_requests or deadline - clock() <= delay + 1:
                break
            if delay:
                sleep(delay)
            timeout = min(args.timeout, max(0.1, deadline - clock() - 0.3))
            print(f"[{len(attempts) + 1}/{args.max_requests}] {format_time(window_start)} to {format_time(window_end)}", flush=True)
            attempt = dict(start=format_time(window_start), end=format_time(window_end), url=url, retry=retry)
            attempts.append(attempt)
            try:
                rows = transport(url, timeout)
                attempt.update(status="ok", count=len(rows))
                interval.pop("error", None)
                interval.update(status="capped" if len(rows) >= args.max_records else "ok", count=len(rows))
                for raw_article in rows:
                    try:
                        article = parse_article(raw_article, format_time(datetime.now(UTC)), window_start, window_end)
                        key = article["canonical_url"]
                        if key in articles:
                            duplicate_urls += 1
                        else:
                            articles[key] = article
                    except (ValueError, TypeError, AttributeError) as error:
                        rejected.append(dict(reason=str(error), record=raw_article))
                if interval["status"] == "capped" and window_end - window_start >= timedelta(minutes=30):
                    mid = window_start + timedelta(seconds=int((window_end - window_start).total_seconds()) // 2)
                    pending.extend([(window_start, mid), (mid, window_end)])
                    interval["status"] = "split"
                break
            except SourceError as error:
                attempt.update(status="failed", error=str(error))
                attempt["connection"] = error.details
                next_request_at = clock() + error.cooldown
                interval.update(status="failed", error=str(error))
                print(f"  {error}", file=sys.stderr, flush=True)
                if not error.retryable:
                    break
            finally:
                last_request = clock()
    saved_articles = sorted(articles.values(), key=lambda a: a["gdelt_seen_at"], reverse=True)
    groups = defaultdict(list)
    for article in saved_articles:
        groups[normalize_title(article["title"])].append(article["url"])
    duplicates = [dict(normalized_title=k, urls=v) for k, v in groups.items() if len(v) > 1]
    incomplete = [x for x in intervals if x["status"] not in {"ok", "split"}]
    return dict(mode="live", query=args.query, window_start=format_time(start), window_end=format_time(end),
                generated_at=format_time(datetime.now(UTC)), complete_query_windows=not incomplete and not rejected,
                limits={**{k: getattr(args, k) for k in ("max_requests", "max_seconds", "timeout", "interval", "retries", "max_records")}, "connect_timeout": connect_timeout},
                attempts=attempts, intervals=intervals, rejected_records=rejected, articles=saved_articles,
                summary=dict(unique_urls=len(saved_articles), distinct_source_hosts=len({a["publisher_host"] for a in saved_articles}),
                             repeated_url_observations=duplicate_urls, possible_duplicate_title_groups=len(duplicates),
                             relevance=dict(Counter(a["relevance"] for a in saved_articles)),
                             observations_by_utc_day=dict(sorted(Counter(a["gdelt_seen_at"][:10] for a in saved_articles).items())),
                             source_hosts=dict(Counter(a["publisher_host"] for a in saved_articles).most_common()),
                             oldest_seen_at=min((a["gdelt_seen_at"] for a in saved_articles), default=None),
                             newest_seen_at=max((a["gdelt_seen_at"] for a in saved_articles), default=None),
                             missing_publication_dates=len(saved_articles),
                             missing_gdelt_domains=sum(not a["gdelt_domain"] for a in saved_articles)),
                possible_duplicate_titles=duplicates)


def render_report(report):
    summary = report["summary"]
    lines = ["# Courtside-Agent GDELT results", "", "Data source: live API",
             f"Window: {report['window_start']} to {report['window_end']}",
             f"Query: `{report['query']}`", "",
             f"Collection: {'All requested windows checked' if report['complete_query_windows'] else 'Incomplete'}",
             f"Requests: {len(report['attempts'])}, unique articles: {summary['unique_urls']}, source domains: {summary['distinct_source_hosts']}",
             f"Possible duplicate headline groups: {summary['possible_duplicate_title_groups']}",
             f"Repeated URL observations (including window overlap): {summary['repeated_url_observations']}",
             f"Title checks: {summary['relevance']}",
             f"Observed timestamp span: {summary['oldest_seen_at']} to {summary['newest_seen_at']}",
             f"Missing verified publication dates: {summary['missing_publication_dates']}",
             f"Rejected records: {len(report['rejected_records'])}", "",
             "These are discovery results, not ranked stories. Hosts are not independent",
             "publishers. Title hints need manual review. Observed timestamps do not verify",
             "publication dates. Uncapped responses do not establish exhaustive NBA coverage.",
             "", "## Query intervals", ""]
    lines += [f"- {x['start']} to {x['end']}: {x['status']} ({x.get('count', 0)} rows){' — ' + x['error'] if x.get('error') else ''}" for x in report["intervals"]]
    for heading, counts in [("Articles by observed date (UTC)", summary["observations_by_utc_day"]), ("Source domains", summary["source_hosts"])]:
        lines += ["", f"## {heading}", ""]
        lines += [f"- {key}: {count}" for key, count in counts.items()]
    lines += ["", "## Review sample (first five per category)", ""]
    for category in ("candidate", "uncertain", "excluded"):
        for a in [a for a in report["articles"] if a["relevance"] == category][:5]:
            lines += [f"- {category}: {a['title']} — {a['publisher_host']} — {a['url']}"]
    lines += ["", "Inspect articles.csv for all titles and report.json for errors, rejected",
              "records, and possible duplicates. Article titles come from external sources.", ""]
    return "\n".join(lines)


def save_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render_report(report), encoding="utf-8")
    fields = ["url", "canonical_url", "title", "publisher_host", "publisher_name", "gdelt_domain", "gdelt_seen_at", "published_at", "collected_at", "language", "source_country", "relevance", "relevance_reason"]
    with (output / "articles.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in report["articles"]:
            # Prevent spreadsheet formulas in exported headlines.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 8), default=7)
    parser.add_argument("--query", default="NBA sourcelang:english")
    parser.add_argument("--window-hours", type=float, default=24)
    parser.add_argument("--max-records", type=int, default=250)
    parser.add_argument("--max-requests", type=int, default=14)
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--connect-timeout", type=float, default=20)
    parser.add_argument("--interval", type=float, default=6)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("artifacts/gdelt-validation"))
    args = parser.parse_args()
    if not (0.25 <= args.window_hours <= 24 and 1 <= args.max_records <= 250 and
            args.max_requests > 0 and args.max_seconds >= 1 and args.timeout >= 1 and args.connect_timeout >= 1 and
            args.interval >= 6 and 0 <= args.retries <= 3 and args.query.strip()):
        parser.error("Require 0.25–24 window hours, 1–250 records, positive budgets, interval >=6, retries 0–3, and a query")
    report = collect_articles(args, datetime.now(UTC).replace(microsecond=0))
    save_report(report, args.output)
    print(render_report(report))
    print(f"Exports: {args.output.resolve()}")
    return 0 if report["complete_query_windows"] else 2


if __name__ == "__main__":
    sys.exit(main())
