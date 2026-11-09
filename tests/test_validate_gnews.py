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

from scripts.validate_gnews import SourceError, UTC, collect_articles, save_report, fetch_page, load_api_key, parse_article

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def row(index=1):
    return dict(title="Lakers announce injury update", url=f"https://example.com/{index}",
                publishedAt="2026-11-07T12:00:00Z", source=dict(name="Example Sports", url="https://example.com"))


def run(transport, max_requests=3):
    args = Namespace(days=3, query="NBA", max_requests=max_requests, max_seconds=90, timeout=30)
    with redirect_stdout(io.StringIO()):
        return collect_articles(args, "private-test-key", NOW, transport, sleep=lambda n: None)


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
        self.assertEqual(article['published_at'], '2026-11-07T12:00:00Z')
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
