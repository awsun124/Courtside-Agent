"""Offline tests: no requests, keys, or sleeps."""
from argparse import Namespace
import csv
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
from contextlib import redirect_stdout, redirect_stderr
from urllib.parse import parse_qs, urlsplit

from scripts.validate_gdelt import (
    UTC, SourceError, canonical_url, collect, decode_response, export, fetch, normalize,
    title_key, triage, windows,
)

END = datetime(2026, 11, 9, tzinfo=UTC)


def row(url="https://www.example.com/news", title="Lakers announce injury update", seen="20261108T120000Z"):
    return dict(url=url, title=title, seendate=seen, domain="different.example", language="English")


class FakeTime:
    def __init__(self):
        self.now = 0
        self.delays = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds


def run(transport, timer=None, **overrides):
    args = Namespace(days=1, window_hours=24, query="NBA sourcelang:english",
                     max_records=250, max_requests=14, max_seconds=180,
                     timeout=20, interval=6, retries=1)
    for key, value in overrides.items():
        setattr(args, key, value)
    timer = timer or FakeTime()
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return collect(args, END, transport, timer.clock, timer.sleep)


class ValidationTests(unittest.TestCase):
    def test_transport_reports_tls_stall_and_uses_requested_timeout(self):
        response = CompletedProcess([], 28, '\n000 0.003 0.049 0.000 30.0', 'curl: (28) SSL connection timeout\n')
        with patch('scripts.validate_gdelt.subprocess.run', return_value=response) as command:
            with self.assertRaises(SourceError) as error:
                fetch('https://api.gdeltproject.org/', 45, connect_timeout=30)
        self.assertEqual(error.exception.details['failure_phase'], 'tls')
        self.assertEqual(error.exception.details['http_status'], 0)
        arguments = command.call_args.args[0]
        self.assertEqual(arguments[arguments.index('--connect-timeout') + 1], '30')
        self.assertNotIn('--insecure', arguments)

    def test_transport_parses_realistic_success_output(self):
        response = CompletedProcess([], 0, '{"articles":[]}\n200 0.01 0.05 0.10 0.25', '')
        with patch('scripts.validate_gdelt.subprocess.run', return_value=response):
            self.assertEqual(fetch('https://api.gdeltproject.org/', 20), [])

    def test_rate_limit_cooldown_applies_to_next_window(self):
        timer, calls = FakeTime(), []
        def transport(url, timeout):
            calls.append(timer.now)
            if len(calls) == 1:
                return decode_response(200, 'Please limit requests to one every 5 seconds')
            return []
        run(transport, timer, days=2, retries=0)
        self.assertGreaterEqual(calls[1] - calls[0], 30)

    def test_rate_limit_even_when_http_success(self):
        for status, body in [(200, "Please limit requests to one every 5 seconds"), (429, "busy")]:
            with self.assertRaises(SourceError) as error:
                decode_response(status, body)
            self.assertTrue(error.exception.retryable)

    def test_schema_errors_are_not_empty_success(self):
        for body in ["not JSON", "{}", '{"articles":null}', "[]"]:
            with self.assertRaises(SourceError):
                decode_response(200, body)
        self.assertEqual(decode_response(200, '{"articles":[]}'), [])

    def test_date_window_rejects_old_future_and_invalid_records(self):
        start = END - timedelta(days=1)
        for seen in ["20261107T235959Z", "20261109T000001Z", "bad-date"]:
            with self.assertRaises(ValueError):
                normalize(row(seen=seen), "collection-time", start, END)
        self.assertEqual(len(list(windows(END - timedelta(days=7), END, 24))), 7)

    def test_attribution_does_not_invent_publisher_or_publication_date(self):
        article = normalize(row(), "collection-time", END - timedelta(days=1), END)
        self.assertEqual(article["publisher_host"], "example.com")
        self.assertEqual(article["gdelt_domain"], "different.example")
        self.assertEqual(article["collected_at"], "collection-time")
        self.assertIsNone(article["publisher_name"])
        self.assertIsNone(article["published_at"])
        self.assertEqual(article["url"], "https://www.example.com/news")

    def test_url_dedup_preserves_meaningful_query_parameters(self):
        a = "https://www.example.com/news?id=10&utm_source=x#top"
        self.assertEqual(canonical_url(a), "https://example.com/news?id=10")
        self.assertNotEqual(canonical_url(a), canonical_url("https://example.com/news?id=11"))
        with self.assertRaises(ValueError):
            canonical_url("javascript:alert(1)")

    def test_duplicates_and_title_groups_keep_separate_urls(self):
        rows = [row(), row(url="https://example.com/news?utm_source=x"),
                row(url="https://other.example/report", title="LAKERS announce injury update!")]
        report = run(lambda url, timeout: rows)
        self.assertEqual(report["summary"]["unique_urls"], 2)
        self.assertEqual(report["summary"]["repeated_url_observations"], 1)
        self.assertEqual(len(report["possible_duplicate_titles"]), 1)
        self.assertEqual(title_key("Bulls &amp; Lakers!"), "bulls lakers")

    def test_relevance_is_conservative_not_player_only_matching(self):
        self.assertEqual(triage("NBA promo code for tonight")[0], "excluded")
        self.assertEqual(triage("Celtics announce a trade")[0], "candidate")
        self.assertEqual(triage("LeBron shares his favorite restaurant")[0], "uncertain")
        self.assertEqual(triage("Thunder storms hit Florida")[0], "uncertain")

    def test_retries_are_paced_and_recovery_clears_error(self):
        timer, calls = FakeTime(), []
        def transport(url, timeout):
            calls.append(timer.now)
            if len(calls) == 1:
                raise SourceError("rate limit", retryable=True)
            return []
        report = run(transport, timer)
        self.assertTrue(report["complete_query_windows"])
        self.assertGreaterEqual(calls[1] - calls[0], 12)
        self.assertNotIn("error", report["intervals"][0])
        self.assertEqual(report["attempts"][0]["status"], "failed")

    def test_request_budget_leaves_windows_explicitly_unattempted(self):
        report = run(lambda url, timeout: [], days=7, max_requests=1)
        self.assertFalse(report["complete_query_windows"])
        self.assertEqual(len(report["attempts"]), 1)
        self.assertEqual(sum(x["status"] == "unattempted" for x in report["intervals"]), 6)

    def test_time_budget_does_not_sleep_past_deadline(self):
        timer = FakeTime()
        report = run(lambda url, timeout: [], timer, days=7, max_seconds=3)
        self.assertEqual(len(report["attempts"]), 1)
        self.assertEqual(timer.delays, [])
        self.assertFalse(report["complete_query_windows"])

    def test_cap_splits_and_requires_both_halves(self):
        def transport(url, timeout):
            p = parse_qs(urlsplit(url).query)
            start = datetime.strptime(p["startdatetime"][0], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            end = datetime.strptime(p["enddatetime"][0], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            if end - start == timedelta(days=1):
                return [row(url="https://example.com/1"), row(url="https://example.com/2")]
            return []
        full = run(transport, max_records=2)
        partial = run(transport, max_records=2, max_requests=2)
        self.assertTrue(full["complete_query_windows"])
        self.assertFalse(partial["complete_query_windows"])
        self.assertEqual([x["status"] for x in full["intervals"]], ["split", "ok", "ok"])

    def test_all_failed_and_malformed_records_are_not_success(self):
        def fail(url, timeout):
            raise SourceError("offline", retryable=True)
        report = run(fail)
        self.assertFalse(report["complete_query_windows"])
        self.assertEqual(len(report["attempts"]), 2)
        self.assertEqual(report["articles"], [])
        malformed = run(lambda url, timeout: [row(seen="bad"), {"url": "missing-title"}])
        self.assertFalse(malformed["complete_query_windows"])
        self.assertEqual(len(malformed["rejected_records"]), 2)

    def test_export_is_readable_and_csv_formula_safe(self):
        report = run(lambda url, timeout: [row(title="=UNTRUSTED()")])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            export(report, output)
            saved = json.loads((output / "report.json").read_text())
            self.assertEqual(saved["articles"][0]["title"], "=UNTRUSTED()")
            with (output / "articles.csv").open() as stream:
                self.assertTrue(next(csv.DictReader(stream))["title"].startswith("'="))
            self.assertIn("ALL WINDOWS UNCAPPED", (output / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
