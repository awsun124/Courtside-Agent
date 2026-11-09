"""Offline tests for GNews collection and private key handling."""
from argparse import Namespace
from contextlib import redirect_stdout
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scripts.validate_gnews import SourceError, UTC, collect_articles, save_report, fetch_page, load_api_key, parse_article

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def row(index=1):
    return dict(title="Lakers announce injury update", url=f"https://example.com/{index}",
                publishedAt="2026-11-08T06:00:00Z", source=dict(name="Example Sports", url="https://example.com"))


def run(transport, max_requests=3, days=1, **options):
    args = Namespace(days=days, query="NBA", max_requests=max_requests, max_seconds=90, timeout=30)
    with redirect_stdout(io.StringIO()):
        return collect_articles(args, "private-test-key", NOW, transport, sleep=lambda n: None, **options)


class GNewsTests(unittest.TestCase):
    def test_key_loading_does_not_execute_env_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            p = Path(folder) / '.env'
            p.write_text('OTHER=$(bad-command)\nGNEWS_API_KEY="test-secret"\n')
            self.assertEqual(load_api_key(p), 'test-secret')
            p.write_text('GNEWS_API_KEY=\n')
            with self.assertRaises(SourceError):
                load_api_key(p)

    def test_transport_sends_key_in_stdin_not_url_or_arguments(self):
        response = CompletedProcess([], 0, '{"totalArticles":0,"articles":[]}\n200', '')
        with patch('scripts.validate_gnews.subprocess.run', return_value=response) as command:
            fetch_page('https://gnews.io/api/v4/search?q=NBA', 'secret-key', 30)
        self.assertNotIn('secret-key', str(command.call_args.args))
        self.assertEqual(command.call_args.kwargs['input'], 'X-Api-Key: secret-key\n')

    def test_failure_response_never_echoes_key(self):
        response = CompletedProcess([], 0, '{"errors":["secret-key"]}\n401', '')
        with patch('scripts.validate_gnews.subprocess.run', return_value=response):
            with self.assertRaises(SourceError) as error:
                fetch_page('https://gnews.io/api/v4/search', 'secret-key', 30)
        self.assertNotIn('secret-key', str(error.exception))

    def test_publication_filter_and_attribution(self):
        article = parse_article(row(), NOW - timedelta(days=3), NOW - timedelta(hours=12), 'collected')
        self.assertEqual(article['publisher_name'], 'Example Sports')
        self.assertEqual(article['published_at'], '2026-11-08T06:00:00Z')
        for date in ['2026-11-01T12:00:00Z', '2026-11-09T00:00:00Z', '2026-11-07T12:00:00']:
            with self.assertRaises(ValueError):
                parse_article({**row(), 'publishedAt': date}, NOW - timedelta(days=3), NOW - timedelta(hours=12), 'collected')

    def test_success_and_explicit_freshness_gap(self):
        r = run(lambda *args: dict(totalArticles=1, articles=[row()]))
        self.assertTrue(r['complete_available_results'])
        self.assertEqual(r['freshness_delay_hours'], 12)
        self.assertNotEqual(r['requested_end'], r['searchable_end'])

    def test_budget_does_not_claim_complete_results(self):
        r = run(lambda *args: dict(totalArticles=100, articles=[row(i) for i in range(10)]), max_requests=1)
        self.assertFalse(r['complete_available_results'])
        self.assertEqual(len(r['attempts']), 1)

    def test_pagination_and_duplicates(self):
        pages = iter([dict(totalArticles=11, articles=[row(i) for i in range(10)]),
                      dict(totalArticles=11, articles=[row(10)])])
        r = run(lambda *args: next(pages))
        self.assertTrue(r['complete_available_results'])
        self.assertEqual(r['summary']['unique_urls'], 11)
        dup = run(lambda *args: dict(totalArticles=2, articles=[row(), row()]))
        self.assertFalse(dup['complete_available_results'])
        self.assertEqual(dup['summary']['duplicate_url_observations'], 1)

    def test_failures_and_rejected_records_are_explicit(self):
        def fail(*args):
            raise SourceError('GNews rate limit')
        r = run(fail)
        self.assertFalse(r['complete_available_results'])
        self.assertEqual(r['attempts'][0]['status'], 'failed')
        bad = run(lambda *args: dict(totalArticles=1, articles=[{}]))
        self.assertEqual(len(bad['rejected_records']), 1)
        self.assertFalse(bad['complete_available_results'])

    def test_three_days_get_separate_windows_before_more_pages(self):
        queries = []
        def transport(url, *args):
            query = parse_qs(urlsplit(url).query)
            queries.append(query)
            return dict(totalArticles=50, articles=[dict(row(len(queries) * 10 + i), publishedAt=query['from'][0]) for i in range(10)])
        result = run(transport, days=3)
        self.assertEqual([query['page'][0] for query in queries], ['1', '1', '1'])
        self.assertEqual(len({query['from'][0] for query in queries}), 3)
        self.assertEqual(result['summary']['unique_urls'], 30)
        self.assertEqual(result['summary']['reported_total'], 150)
        self.assertFalse(result['complete_available_results'])
        self.assertEqual(result['rejected_records'], [])

    def test_small_budget_still_spans_the_entire_week(self):
        result = run(lambda *args: dict(totalArticles=0, articles=[]), days=7)
        windows = sorted(result['windows'], key=lambda window: window['start'])
        self.assertEqual(windows[0]['start'], result['requested_start'])
        self.assertEqual(windows[-1]['end'], result['searchable_end'])
        for left, right in zip(windows, windows[1:]):
            end = datetime.fromisoformat(left['end'].replace('Z', '+00:00'))
            start = datetime.fromisoformat(right['start'].replace('Z', '+00:00'))
            self.assertEqual(start - end, timedelta(microseconds=1))
        self.assertTrue(result['complete_available_results'])

    def test_second_pages_wait_until_each_window_has_been_queried(self):
        pages = []
        def transport(url, *args):
            query = parse_qs(urlsplit(url).query)
            pages.append(int(query['page'][0]))
            return dict(totalArticles=100, articles=[dict(row(len(pages) * 10 + i), publishedAt=query['from'][0]) for i in range(10)])
        run(transport, max_requests=5, days=3)
        self.assertEqual(pages, [1, 1, 1, 2, 2])

    def test_article_outside_its_window_is_rejected(self):
        result = run(lambda *args: dict(totalArticles=1, articles=[row()]), days=3)
        self.assertGreater(len(result['rejected_records']), 0)
        self.assertFalse(result['complete_available_results'])

    def test_failed_window_keeps_earlier_results_and_unknown_total(self):
        calls = []
        def transport(url, *args):
            calls.append(url)
            if len(calls) == 2:
                raise SourceError('GNews rate limit')
            query = parse_qs(urlsplit(url).query)
            return dict(totalArticles=1, articles=[dict(row(), publishedAt=query['from'][0])])
        result = run(transport, days=3)
        self.assertEqual(len(result['articles']), 1)
        self.assertEqual(len(calls), 2)
        self.assertIsNone(result['summary']['reported_total'])
        self.assertFalse(result['complete_available_results'])

    def test_exports_redact_key_and_preserve_original_urls(self):
        r = run(lambda *args: dict(totalArticles=1, articles=[row()]))
        r['query'] = 'private-test-key'
        with tempfile.TemporaryDirectory() as folder:
            save_report(r, Path(folder), 'private-test-key')
            for p in Path(folder).iterdir():
                self.assertNotIn('private-test-key', p.read_text())
            saved = json.loads((Path(folder) / 'report.json').read_text())
            self.assertEqual(saved['articles'][0]['url'], 'https://example.com/1')


if __name__ == '__main__':
    unittest.main()
