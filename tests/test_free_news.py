"""Check source attribution, limits, date handling, and isolated API failures."""
from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from courtside.free_news import collect_headlines, fetch_page, load_key, parse_article
from courtside.sources import collect_sources, merge_articles, plan_searches
from courtside.stories import inspect_article
from courtside.ranking import reporting_groups
from scripts.validate_gdelt import SourceError

NOW = datetime(2026, 11, 11, 6, tzinfo=timezone.utc)
START = NOW - timedelta(days=7)
SETTINGS = dict(max_requests=2, max_articles_per_publisher=2,
                publishers={'alpha.example.com': 'Alpha Sports', 'bravo.example.com': 'Bravo Sports'})


def row(host='alpha.example.com', **changes):
    return dict(title='Lakers beat Celtics 110-100 in NBA game', url=f'https://{host}/nba/game', host=host,
                sitename='Misleading publisher label', published_at='2026-11-11T05:00:00Z',
                description='Article text that must not be retained or sent to AI', text='Full article body', **changes)


class FreeNewsTests(unittest.TestCase):
    def test_key_is_loaded_as_data_without_shell_expansion(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            path = Path(folder) / '.env'
            path.write_text('OTHER=$(ignored)\nFREE_NEWS_API_KEY="fna_private_test_key"\n')
            self.assertEqual(load_key(path), 'fna_private_test_key')
            path.write_text('FREE_NEWS_API_KEY=bad key\n')
            with self.assertRaises(SourceError):
                load_key(path)
            path.write_text('')
            self.assertIsNone(load_key(path))

    def test_only_attributed_metadata_is_retained(self):
        saved = parse_article(row(), SETTINGS['publishers'], START, NOW, NOW.isoformat())
        self.assertEqual(saved['publisher_name'], 'Alpha Sports')
        self.assertEqual(saved['publisher_host'], 'alpha.example.com')
        self.assertEqual(saved['url'], row()['url'])
        self.assertEqual(saved['collected_at'], NOW.isoformat())
        self.assertIn('not supplied', saved['publication_date_basis'])
        self.assertIsNone(saved['description'])
        self.assertIsNone(saved['content_excerpt'])
        self.assertNotIn('text', saved)
        self.assertFalse(saved['investigation_allowed'])

    def test_future_old_crawl_dates_and_mismatched_hosts_are_rejected(self):
        for changes in [dict(published_at='2026-11-11T06:01:00Z'), dict(published_at=NOW.isoformat()),
                        dict(published_at='2026-11-01T00:00:00Z'), dict(published_at='2026-11-10'),
                        dict(date_source='crawled'), dict(date_source='crawled_clamped'),
                        dict(host='wrong.example.com'), dict(url=[]), dict(url='https://unknown.example.com/nba/game')]:
            with self.subTest(changes=changes), self.assertRaises((ValueError, KeyError)):
                parse_article({**row(), **changes}, SETTINGS['publishers'], START, NOW, NOW.isoformat())
        accepted = parse_article({**row(), 'published_at': START.isoformat(), 'date_source': 'jsonld'},
                                 SETTINGS['publishers'], START, NOW, NOW.isoformat())
        self.assertIn('jsonld', accepted['publication_date_basis'])

    def test_exact_api_host_survives_url_normalization(self):
        saved = parse_article(row('www.cbssports.com'), {'www.cbssports.com': 'CBS Sports'}, START, NOW, NOW.isoformat())
        self.assertEqual(saved['publisher_name'], 'CBS Sports')
        self.assertEqual(saved['publisher_host'], 'cbssports.com')
        self.assertEqual(saved['canonical_url'], 'https://cbssports.com/nba/game')

    def test_explicit_wire_attribution_counts_together(self):
        first = parse_article(row(author='AP News'), SETTINGS['publishers'], START, NOW, NOW.isoformat())
        second = parse_article({**row('bravo.example.com'), 'title': 'Lakers defeat Celtics 110-100', 'author': 'Associated Press'},
                               SETTINGS['publishers'], START, NOW, NOW.isoformat())
        for article in (first, second):
            article['publisher_id'] = article['publisher_name'].lower()
        self.assertEqual(len(reporting_groups([first, second])), 1)

    def test_batches_keep_dates_keys_limits_and_duplicates_under_control(self):
        calls = []
        def transport(url, key, timeout):
            query = parse_qs(urlsplit(url).query)
            calls.append(query)
            self.assertNotIn(key, url)
            self.assertTrue(query['from'][0].endswith('Z'))
            self.assertTrue(query['to'][0].endswith('Z'))
            self.assertEqual(query['full_text'], ['false'])
            host = query['host'][0]
            entries = [row(host), row(host)]
            entries += [{**row(host), 'url': f'https://{host}/nba/{index}'} for index in range(4)]
            entries += [{**row(host), 'url': f'https://{host}/betting/promo', 'title': 'NBA promo code best bets'}]
            return dict(results=entries)
        articles, status, attempts = collect_headlines('fna_private_test_key', START, NOW, SETTINGS,
            transport=transport, sleep=lambda _: None)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]['host'], calls[1]['host'])
        self.assertEqual(len(articles), 4)
        self.assertEqual(status['status'], 'partial')
        self.assertEqual(status['filtered_records'], 2)
        self.assertEqual(status['capped_records'], 6)
        self.assertEqual(len(attempts), 2)
        self.assertFalse(status['complete_window'])

    def test_quota_errors_are_generic_and_do_not_retry(self):
        response = CompletedProcess([], 0, '{"error":"fna_private_test_key"}\n402', '')
        with patch('courtside.free_news.subprocess.run', return_value=response) as request:
            with self.assertRaises(SourceError) as error:
                fetch_page('https://freenewsapi.ai/v1/search?q=NBA', 'fna_private_test_key', 1)
        self.assertIn('quota', str(error.exception))
        self.assertNotIn('fna_private_test_key', str(error.exception))
        self.assertNotIn('fna_private_test_key', ' '.join(request.call_args.args[0]))
        self.assertEqual(request.call_count, 1)
        calls = []
        def fail(*args):
            calls.append(1)
            raise SourceError('fna_private_test_key')
        articles, status, attempts = collect_headlines('fna_private_test_key', START, NOW, SETTINGS, transport=fail)
        self.assertEqual(len(calls), 1)
        self.assertFalse(articles)
        self.assertNotIn('fna_private_test_key', json.dumps([status, attempts]))

    def test_time_budget_does_not_send_a_request(self):
        with patch('courtside.free_news.fetch_page') as network:
            articles, status, attempts = collect_headlines('private-test-key', START, NOW, SETTINGS, max_seconds=0)
        network.assert_not_called()
        self.assertEqual(status['status'], 'skipped')
        self.assertEqual(attempts, [])

    def test_metadata_copy_preserves_independently_acquired_material(self):
        metadata = parse_article(row(), SETTINGS['publishers'], START, NOW, NOW.isoformat())
        permitted = {**metadata, 'metadata_only': False, 'investigation_allowed': True,
                     'collection_sources': ['gnews'], 'description': 'Permitted API excerpt'}
        for records in ([metadata, permitted], [permitted, metadata]):
            merged = merge_articles(records)
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]['description'], 'Permitted API excerpt')
            self.assertTrue(merged[0]['investigation_allowed'])
            self.assertEqual(merged[0]['collection_sources'], ['free-news-api', 'gnews'])

    def test_source_can_run_without_gnews_and_logs_partial_coverage(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            env = Path(folder) / '.env'
            env.write_text('FREE_NEWS_API_KEY=fna_private_test_key\n')
            sources = Path(folder) / 'sources.json'
            sources.write_text('{"feeds": []}')
            def transport(url, key, timeout):
                host = parse_qs(urlsplit(url).query)['host'][0].split(',')[0]
                return dict(results=[row(host)])
            args = Namespace(days=7, query='NBA', max_requests=1, max_seconds=90, timeout=30)
            report = collect_sources(args, None, NOW, sources, env_file=env,
                                     free_news_transport=transport, sleep=lambda _: None)
        self.assertEqual(len(report['attempts']), 3)
        self.assertEqual(len(report['articles']), 2)
        self.assertFalse(report['complete_available_results'])
        free_status = next(s for s in report['sources'] if s['id'] == 'free-news-api')
        self.assertEqual(free_status['missing_date_provenance'], len(report['articles']))
        activity = next(x for x in report['collection_activity'] if x['source_id'] == 'free-news-api')
        self.assertEqual(activity['requests'], 2)
        self.assertEqual(activity['status'], 'partial')

    def test_search_cooldowns_are_separate_for_each_provider(self):
        article = parse_article(row(), SETTINGS['publishers'], START, NOW, NOW.isoformat())
        history = [dict(data_mode='live', as_of=(NOW - timedelta(hours=1)).isoformat(), collection_activity=[
            dict(source_id='free-news-api', purpose='corroboration', query='celtics lakers', requests=1,
                 reporting_groups_added=0, status='partial')])]
        free = plan_searches([article], NOW, NOW, history, source_id='free-news-api')
        gnews = plan_searches([article], NOW, NOW, history)
        self.assertTrue(free[0]['skip_reason'])
        self.assertIsNone(gnews[0]['skip_reason'])

    def test_side_event_and_historical_trade_mentions_do_not_count(self):
        for title in ['Warriors jersey swap follows NBA win over Pelicans',
                      'Jaylen Brown Confronted Jayson Tatum Before Celtics Blockbuster Trade: Shams',
                      'Warriors urged to trade for two NBA wings',
                      'Bucks shed salary in NBA trade proposal',
                      'Luka Doncic Ruthlessly Mocks Hawks Fans During Lakers Win',
                      'Lakers star Austin Reaves perfectly sums up win vs Pistons',
                      "Three Things the Box Score Won't Tell You About the Hawks Loss to Lakers"]:
            saved = parse_article({**row(), 'title': title}, SETTINGS['publishers'], START, NOW, NOW.isoformat())
            self.assertEqual(inspect_article(saved)[0], 'review', title)

    def test_injury_subject_suffix_and_uncertain_absence_are_preserved(self):
        cases = [('Pelicans Trey Murphy III ruled out for Warriors clash with knee injury', 'trey murphy', 'unavailable'),
                 ('Warriors Brandon Williams Could Miss Extended Time After Hamstring Injury', 'brandon williams', 'uncertain')]
        for title, subject, availability in cases:
            saved = parse_article({**row(), 'title': title}, SETTINGS['publishers'], START, NOW, NOW.isoformat())
            decision, _, features = inspect_article(saved)
            self.assertEqual(decision, 'included', title)
            self.assertEqual(features['subjects'], [subject])
            self.assertEqual(features['injury_availability'], availability)

    def test_failed_api_preserves_successful_feed_results(self):
        body = b'<rss><channel><item><title>Lakers beat Celtics 110-100 in NBA game</title><link>https://sports.yahoo.com/nba/game</link><pubDate>Wed, 11 Nov 2026 05:00:00 GMT</pubDate></item></channel></rss>'
        def fail(*args):
            raise SourceError('private provider error')
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            env = Path(folder) / '.env'
            env.write_text('FREE_NEWS_API_KEY=fna_private_test_key\n')
            args = Namespace(days=7, query='NBA', max_requests=1, max_seconds=90, timeout=30)
            report = collect_sources(args, None, NOW, env_file=env, free_news_transport=fail,
                                     feed_transport=lambda *args: body)
        self.assertEqual(len(report['articles']), 1)
        self.assertEqual(report['articles'][0]['publisher_name'], 'Yahoo Sports')
        self.assertEqual(next(s for s in report['sources'] if s['id'] == 'free-news-api')['status'], 'failed')
        self.assertNotIn('private provider error', json.dumps(report))


if __name__ == '__main__':
    unittest.main()
