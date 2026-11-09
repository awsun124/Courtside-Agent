"""Bounded GDELT metadata evaluation using the standard library and curl."""
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


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_seen(value):
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


def title_key(title):
    return " ".join(re.findall(r"\w+", html.unescape(title).casefold()))


def triage(title):
    text = title_key(title)
    if re.search(r"\b(promo code|referral code|best bets|betting promos|sportsbook bonus)\b", text):
        return "excluded", "promotional/betting title"
    if re.search(r"\b(nba|national basketball association|lakers|celtics|knicks|76ers|sixers|"
                 r"mavericks|cavaliers|timberwolves|pelicans|grizzlies|clippers|raptors|"
                 r"trail blazers|brooklyn nets|golden state warriors|oklahoma city thunder|"
                 r"miami heat|chicago bulls|milwaukee bucks|denver nuggets|indiana pacers|houston rockets|"
                 r"detroit pistons|atlanta hawks|charlotte hornets|orlando magic|phoenix suns|"
                 r"sacramento kings|san antonio spurs|utah jazz|washington wizards)\b", text):
        return "candidate", "NBA/team title cue; event relevance unverified"
    return "uncertain", "no unambiguous NBA title cue; manual review required"


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
        data = json.loads(body)
    except ValueError:
        raise SourceError("Non-JSON response: " + body[:180].replace("\n", " ")) from None
    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        raise SourceError("JSON response missing articles array")
    return data["articles"]


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


def windows(start, end, hours):
    while start < end:
        stop = min(end, start + timedelta(hours=hours))
        yield start, stop
        start = stop


def normalize(raw, collected_at, start, end):
    if not isinstance(raw, dict):
        raise ValueError("article is not an object")
    url, title = raw.get("url"), raw.get("title")
    if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
        raise ValueError("missing URL/title")
    canonical = canonical_url(url)
    seen = parse_seen(raw.get("seendate", ""))
    if not start <= seen <= end:
        raise ValueError("observed timestamp outside response window")
    relevance, reason = triage(title)
    return dict(url=url, canonical_url=canonical, title=html.unescape(title).strip(),
                publisher_host=urlsplit(canonical).hostname, publisher_name=None,
                gdelt_domain=raw.get("domain"), gdelt_seen_at=iso(seen),
                published_at=None, collected_at=collected_at,
                language=raw.get("language"), source_country=raw.get("sourcecountry"),
                relevance=relevance, relevance_reason=reason)


def collect(args, end, transport=None, clock=time.monotonic, sleep=time.sleep):
    connect_timeout = getattr(args, "connect_timeout", 20)
    if transport is None:
        transport = lambda url, timeout: fetch(url, timeout, connect_timeout)
    start = end - timedelta(days=args.days)
    pending = deque(windows(start, end, args.window_hours))
    deadline, last_request = clock() + args.max_seconds, None
    next_allowed = 0
    attempts, intervals, articles, rejected = [], [], {}, []
    duplicate_urls = 0
    while pending:
        lo, hi = pending.popleft()
        interval = dict(start=iso(lo), end=iso(hi), status="unattempted")
        intervals.append(interval)
        params = dict(query=args.query, mode="artlist", format="json", sort="datedesc",
                      maxrecords=args.max_records, startdatetime=lo.strftime("%Y%m%d%H%M%S"),
                      enddatetime=hi.strftime("%Y%m%d%H%M%S"))
        url = ENDPOINT + "?" + urlencode(params)
        for retry in range(args.retries + 1):
            delay = 0 if last_request is None else max(0, last_request + args.interval * (2 ** retry) - clock())
            delay = max(delay, next_allowed - clock())
            if len(attempts) >= args.max_requests or deadline - clock() <= delay + 1:
                break
            if delay:
                sleep(delay)
            timeout = min(args.timeout, max(0.1, deadline - clock() - 0.3))
            print(f"[{len(attempts) + 1}/{args.max_requests}] {iso(lo)} to {iso(hi)}", flush=True)
            attempt = dict(start=iso(lo), end=iso(hi), url=url, retry=retry)
            attempts.append(attempt)
            try:
                rows = transport(url, timeout)
                attempt.update(status="ok", count=len(rows))
                interval.pop("error", None)
                interval.update(status="capped" if len(rows) >= args.max_records else "ok", count=len(rows))
                for raw in rows:
                    try:
                        article = normalize(raw, iso(datetime.now(UTC)), lo, hi)
                        key = article["canonical_url"]
                        if key in articles:
                            duplicate_urls += 1
                        else:
                            articles[key] = article
                    except (ValueError, TypeError, AttributeError) as error:
                        rejected.append(dict(reason=str(error), record=raw))
                if interval["status"] == "capped" and hi - lo >= timedelta(minutes=30):
                    mid = lo + timedelta(seconds=int((hi - lo).total_seconds()) // 2)
                    pending.extend([(lo, mid), (mid, hi)])
                    interval["status"] = "split"
                break
            except SourceError as error:
                attempt.update(status="failed", error=str(error))
                attempt["connection"] = error.details
                next_allowed = clock() + error.cooldown
                interval.update(status="failed", error=str(error))
                print(f"  {error}", file=sys.stderr, flush=True)
                if not error.retryable:
                    break
            finally:
                last_request = clock()
    values = sorted(articles.values(), key=lambda a: a["gdelt_seen_at"], reverse=True)
    groups = defaultdict(list)
    for article in values:
        groups[title_key(article["title"])].append(article["url"])
    duplicates = [dict(normalized_title=k, urls=v) for k, v in groups.items() if len(v) > 1]
    incomplete = [x for x in intervals if x["status"] not in {"ok", "split"}]
    return dict(mode="live", query=args.query, window_start=iso(start), window_end=iso(end),
                generated_at=iso(datetime.now(UTC)), complete_query_windows=not incomplete and not rejected,
                limits={**{k: getattr(args, k) for k in ("max_requests", "max_seconds", "timeout", "interval", "retries", "max_records")}, "connect_timeout": connect_timeout},
                attempts=attempts, intervals=intervals, rejected_records=rejected, articles=values,
                summary=dict(unique_urls=len(values), distinct_source_hosts=len({a["publisher_host"] for a in values}),
                             repeated_url_observations=duplicate_urls, possible_duplicate_title_groups=len(duplicates),
                             relevance=dict(Counter(a["relevance"] for a in values)),
                             observations_by_utc_day=dict(sorted(Counter(a["gdelt_seen_at"][:10] for a in values).items())),
                             source_hosts=dict(Counter(a["publisher_host"] for a in values).most_common()),
                             oldest_seen_at=min((a["gdelt_seen_at"] for a in values), default=None),
                             newest_seen_at=max((a["gdelt_seen_at"] for a in values), default=None),
                             missing_publication_dates=len(values),
                             missing_gdelt_domains=sum(not a["gdelt_domain"] for a in values)),
                possible_duplicate_titles=duplicates)


def render_report(report):
    s = report["summary"]
    lines = ["# Court Side — GDELT validation", "", "Mode: LIVE (no sample fallback)",
             f"Window: {report['window_start']} to {report['window_end']}",
             f"Query: `{report['query']}`", "",
             f"Query coverage: {'ALL WINDOWS UNCAPPED' if report['complete_query_windows'] else 'PARTIAL / UNVERIFIED'}",
             f"HTTP attempts: {len(report['attempts'])}; unique URLs: {s['unique_urls']}; source hosts: {s['distinct_source_hosts']}",
             f"Possible duplicate headline groups: {s['possible_duplicate_title_groups']}",
             f"Repeated URL observations (including window overlap): {s['repeated_url_observations']}",
             f"Title-only relevance hints: {s['relevance']}",
             f"Observed timestamp span: {s['oldest_seen_at']} to {s['newest_seen_at']}",
             f"Missing verified publication dates: {s['missing_publication_dates']}",
             f"Rejected records: {len(report['rejected_records'])}", "",
             "These are discovery results, not ranked stories. Hosts are not independent",
             "publishers. Title hints need manual review. Observed timestamps do not verify",
             "publication dates. Uncapped responses do not establish exhaustive NBA coverage.",
             "", "## Query intervals", ""]
    lines += [f"- {x['start']} to {x['end']}: {x['status']} ({x.get('count', 0)} rows){' — ' + x['error'] if x.get('error') else ''}" for x in report["intervals"]]
    for heading, counts in [("Observed UTC days", s["observations_by_utc_day"]), ("Source hosts", s["source_hosts"])]:
        lines += ["", f"## {heading}", ""]
        lines += [f"- {key}: {count}" for key, count in counts.items()]
    lines += ["", "## Review sample (first five per category)", ""]
    for category in ("candidate", "uncertain", "excluded"):
        for a in [a for a in report["articles"] if a["relevance"] == category][:5]:
            lines += [f"- {category}: {a['title']} — {a['publisher_host']} — {a['url']}"]
    lines += ["", "Inspect articles.csv for all titles and report.json for errors, rejected",
              "records, duplicate groups, and provenance. External titles are untrusted data.", ""]
    return "\n".join(lines)


def export(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render_report(report), encoding="utf-8")
    fields = ["url", "canonical_url", "title", "publisher_host", "publisher_name", "gdelt_domain", "gdelt_seen_at", "published_at", "collected_at", "language", "source_country", "relevance", "relevance_reason"]
    with (output / "articles.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in report["articles"]:
            # Guard spreadsheet users against formulas in untrusted headline text.
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
    report = collect(args, datetime.now(UTC).replace(microsecond=0))
    export(report, args.output)
    print(render_report(report))
    print(f"Exports: {args.output.resolve()}")
    return 0 if report["complete_query_windows"] else 2


if __name__ == "__main__":
    sys.exit(main())
