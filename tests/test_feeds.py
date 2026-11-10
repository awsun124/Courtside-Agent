"""Check feed boundaries, attribution, and source failures without network access."""
from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from courtside.feeds import collect_feeds, load_sources, parse_feed
from courtside.sources import collect_sources, corroboration_query, merge_articles
from courtside.stories import process_report
from scripts.validate_gnews import SourceError

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
START = NOW - timedelta(days=3)


def feed(items=None):
    return ('<rss><channel>' + (items if items is not None else item()) + '</channel></rss>').encode()


def item(title='Lakers beat Pistons 110-102', date='Mon, 09 Nov 2026 10:00:00 GMT', link='https://sports.yahoo.com/nba/game.html', extra=''):
    return f'<item><title>{title}</title><link>{link}</link><pubDate>{date}</pubDate>{extra}</item>'


class FeedTests(unittest.TestCase):
    def parse(self, body):
        return parse_feed(body, 'yahoo-nba', START, NOW, NOW.isoformat())

    def test_metadata_is_attributed_without_copying_bodies(self):
        body = feed(item(title='Lakers win &amp; Pistons lose', extra='<description>Hidden description</description><encoded>Full article text</encoded>'))
        saved = self.parse(body)['articles'][0]
        self.assertEqual(saved['title'], 'Lakers win & Pistons lose')
        self.assertEqual(saved['publisher_name'], 'Yahoo Sports')
        self.assertEqual(saved['url'], 'https://sports.yahoo.com/nba/game.html')
        self.assertEqual(saved['published_at'], '2026-11-09T10:00:00Z')
        self.assertEqual(saved['collected_at'], NOW.isoformat())
        self.assertIsNone(saved['description'])
        self.assertIsNone(saved['content_excerpt'])
        self.assertFalse(saved['investigation_allowed'])

    def test_outside_dates_and_invalid_items_are_separate(self):
        body = feed(item(date='Mon, 02 Nov 2026 12:00:00 GMT') + item(date='Tue, 10 Nov 2026 12:00:00 GMT') + item(date='not a date') + item(link='javascript:alert(1)') + item(link='https://other.com/article') + item())
        result = self.parse(body)
        self.assertEqual(result['outside_window'], 2)
        self.assertEqual(result['rejected_records'], 3)
        self.assertEqual(len(result['articles']), 1)

    def test_boundaries_are_inclusive_and_timezones_normalized(self):
        result = self.parse(feed(item(date='Fri, 06 Nov 2026 07:00:00 -0500') + item(date='Mon, 09 Nov 2026 12:00:00 GMT')))
        self.assertEqual(len(result['articles']), 2)
        self.assertEqual(result['articles'][0]['published_at'], '2026-11-06T12:00:00Z')

    def test_unsafe_xml_html_and_oversized_responses_fail(self):
        for body in [b'<!DOCTYPE rss [<!ENTITY e "boom">]><rss/>', b'<html/>', b'<rss>', b'x' * 2000001, b'\x00<rss/>']:
            with self.subTest(body_length=len(body)), self.assertRaises(SourceError):
                self.parse(body)

    def test_source_configuration_rejects_unreviewed_and_arbitrary_endpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sources.json'
            for feeds in [[{'id': 'espn-nba', 'enabled': True}], [{'id': 'http://localhost', 'enabled': True}], [{'id': 'yahoo-nba', 'enabled': 'true'}], [{'id': 'yahoo-nba', 'enabled': True}] * 2]:
                path.write_text(json.dumps({'feeds': feeds}))
                with self.assertRaises(ValueError):
                    load_sources(path)
            path.write_text(json.dumps({'feeds': [{'id': 'yahoo-nba', 'enabled': True}, {'id': 'espn-nba', 'enabled': False}]}))
            self.assertEqual(load_sources(path), ['yahoo-nba'])

    def test_failed_feed_has_no_success_timestamp(self):
        def fail(*args):
            raise SourceError('Feed unavailable')
        articles, statuses, attempts = collect_feeds(['yahoo-nba'], START, NOW, transport=fail)
        self.assertEqual(articles, [])
        self.assertEqual(statuses[0]['status'], 'failed')
        self.assertIsNone(statuses[0]['collected_at'])
        self.assertEqual(len(attempts), 1)

    def test_expired_budget_does_not_call_transport(self):
        with patch('courtside.feeds.fetch_feed') as transport:
            articles, statuses, attempts = collect_feeds(['yahoo-nba'], START, NOW, transport=transport, clock=iter([0, 30]).__next__)
        transport.assert_not_called()
        self.assertEqual(statuses[0]['status'], 'skipped')
        self.assertEqual(attempts, [])

    def test_feed_only_collection_and_processing_need_no_key(self):
        args = Namespace(days=3, query='NBA', max_requests=1, max_seconds=90, timeout=30)
        report = collect_sources(args, None, NOW, feed_transport=lambda *args: feed())
        self.assertEqual(report['sources'][0]['status'], 'unconfigured')
        self.assertEqual(report['sources'][1]['status'], 'ok')
        self.assertEqual(len(report['attempts']), 1)
        self.assertFalse(report['complete_available_results'])
        result = process_report(report)
        self.assertEqual(result['source'], 'Monitored sources')
        self.assertEqual(result['articles'][0]['decision'], 'included')
        self.assertEqual(result['window_end'], '2026-11-09T12:00:00Z')

    def test_feed_failure_does_not_discard_successful_api_results(self):
        args = Namespace(days=1, query='NBA', max_requests=1, max_seconds=90, timeout=30)
        def fail(*args):
            raise SourceError('Feed unavailable')
        def news(*args):
            return {'totalArticles': 1, 'articles': [{'title':'Lakers beat Pistons 110-102', 'url':'https://example.com/game', 'publishedAt':'2026-11-08T18:00:00Z', 'source':{'name':'Example Sports'}}]}
        report = collect_sources(args, 'private-test-key', NOW, feed_transport=fail, news_transport=news)
        self.assertEqual(len(report['articles']), 1)
        self.assertEqual(report['sources'][1]['status'], 'failed')
        self.assertEqual(report['sources'][0]['status'], 'ok')
        self.assertNotIn('private-test-key', json.dumps(report))

    def test_api_only_window_does_not_claim_the_latest_twelve_hours(self):
        args = Namespace(days=1, query='NBA', max_requests=1, max_seconds=90, timeout=30)
        def news(*args):
            return {'totalArticles': 0, 'articles': []}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sources.json'
            path.write_text('{"feeds": []}')
            report = collect_sources(args, 'test-key', NOW, sources_file=path, news_transport=news)
        self.assertEqual(report['searchable_end'], '2026-11-09T00:00:00Z')
        self.assertEqual(len(report['sources']), 1)
        self.assertEqual(len(report['attempts']), 1)

    def test_api_failure_does_not_discard_successful_feed(self):
        args = Namespace(days=3, query='NBA', max_requests=1, max_seconds=90, timeout=30)
        def fail(*args):
            raise SourceError('API unavailable')
        report = collect_sources(args, 'private-test-key', NOW, feed_transport=lambda *args: feed(), news_transport=fail)
        self.assertEqual(len(report['articles']), 1)
        self.assertEqual(report['sources'][0]['status'], 'failed')
        self.assertEqual(report['sources'][1]['status'], 'ok')

    def test_total_source_failure_raises_instead_of_returning_sample_data(self):
        args = Namespace(days=3, query='NBA', max_requests=1, max_seconds=90, timeout=30)
        def fail(*args):
            raise SourceError('Unavailable')
        with self.assertRaises(SourceError):
            collect_sources(args, None, NOW, feed_transport=fail)

    def test_corroboration_uses_existing_budget_and_preserves_publishers(self):
        queries = []
        def news(url, *unused):
            queries.append(parse_qs(urlsplit(url).query)['q'][0])
            index = len(queries)
            return {'totalArticles': 1, 'articles': [{
                'title': 'NBA Lakers beat Pistons 110-102' if index == 1 else 'NBA Pistons lost to Lakers 102-110',
                'url': f'https://publisher{index}.com/game', 'publishedAt': '2026-11-08T18:00:00Z',
                'source': {'name': f'Publisher {index}'}}]}
        args = Namespace(days=3, query='NBA', max_requests=2, max_seconds=90, timeout=30)
        report = collect_sources(args, 'test-key', NOW, feed_transport=lambda *args: feed(),
                                 news_transport=news, sleep=lambda seconds: None)
        self.assertEqual(queries[0], 'NBA')
        self.assertEqual(set(queries[1].split()), {'lakers', 'pistons'})
        self.assertEqual(len(report['attempts']), 3)
        self.assertEqual(report['attempts'][-1]['purpose'], 'corroboration')
        self.assertFalse(report['complete_available_results'])
        result = process_report(report)
        game = next(story for story in result['stories'] if 'Publisher 2' in story['publishers'])
        self.assertIn('Publisher 1', game['publishers'])
        self.assertGreaterEqual(game['reporting_groups'], 2)

    def test_recent_feed_games_do_not_trigger_unavailable_corroboration(self):
        queries = []
        def news(url, *unused):
            queries.append(parse_qs(urlsplit(url).query)['q'][0])
            return {'totalArticles': 0, 'articles': []}
        args = Namespace(days=3, query='NBA', max_requests=2, max_seconds=90, timeout=30)
        collect_sources(args, 'test-key', NOW, feed_transport=lambda *args: feed(),
                        news_transport=news, sleep=lambda seconds: None)
        self.assertEqual(queries, ['NBA'])

    def test_injury_corroboration_uses_player_and_body_part_within_budget(self):
        queries = []
        def news(url, *unused):
            queries.append(parse_qs(urlsplit(url).query)['q'][0])
            index = len(queries)
            return {'totalArticles': 1, 'articles': [{
                'title': 'Marcus Reed ruled out for Lakers with ankle injury' if index == 1 else 'Marcus Reed cleared to play for Lakers after ankle sprain',
                'description': 'An NBA ankle injury update.',
                'url': f'https://publisher{index}.com/injury', 'publishedAt': f'2026-11-08T{17+index}:00:00Z',
                'source': {'name': f'Publisher {index}'}}]}
        args = Namespace(days=3, query='NBA', max_requests=2, max_seconds=90, timeout=30)
        report = collect_sources(args, 'test-key', NOW, feed_transport=lambda *args: feed(),
                                 news_transport=news, sleep=lambda seconds: None)
        self.assertEqual(queries, ['NBA', 'marcus reed ankle injury'])
        self.assertEqual(len(report['attempts']), 3)
        injuries = [story for story in process_report(report)['stories'] if story['event'] == 'injury']
        self.assertEqual(len(injuries), 1)
        self.assertEqual(injuries[0]['reporting_groups'], 2)

    def test_vague_or_recent_injuries_do_not_trigger_a_targeted_search(self):
        for title, date in [('Lakers announce Marcus Reed injury news', 'Sun, 08 Nov 2026 18:00:00 GMT'),
                            ('Marcus Reed ruled out for Lakers with ankle injury', 'Mon, 09 Nov 2026 10:00:00 GMT')]:
            with self.subTest(title=title):
                articles = self.parse(feed(item(title=title, date=date)))['articles']
                self.assertIsNone(corroboration_query(articles, NOW - timedelta(hours=12)))

    def test_failed_corroboration_keeps_discovery_and_does_not_retry(self):
        calls = []
        def news(url, *unused):
            calls.append(url)
            if len(calls) == 2:
                raise SourceError('GNews rate or quota limit reached')
            return {'totalArticles': 1, 'articles': [{
                'title': 'NBA Lakers beat Pistons 110-102', 'url': 'https://example.com/game',
                'publishedAt': '2026-11-08T18:00:00Z', 'source': {'name': 'Example Sports'}}]}
        args = Namespace(days=3, query='NBA', max_requests=2, max_seconds=90, timeout=30)
        report = collect_sources(args, 'test-key', NOW, feed_transport=lambda *args: feed(),
                                 news_transport=news, sleep=lambda seconds: None)
        self.assertEqual(len(calls), 2)
        self.assertEqual(report['sources'][0]['status'], 'partial')
        self.assertEqual(len(report['articles']), 2)
        self.assertEqual(report['attempts'][-1]['status'], 'failed')

    def test_expired_budget_after_pause_skips_corroboration(self):
        elapsed = [0]
        calls = []
        def news(url, *unused):
            calls.append(url)
            return {'totalArticles': 1, 'articles': [{
                'title': 'NBA Lakers beat Pistons 110-102', 'url': 'https://example.com/game',
                'publishedAt': '2026-11-08T18:00:00Z', 'source': {'name': 'Example Sports'}}]}
        def pause(seconds):
            elapsed[0] = 100
        args = Namespace(days=3, query='NBA', max_requests=2, max_seconds=90, timeout=30)
        report = collect_sources(args, 'test-key', NOW, feed_transport=lambda *args: feed(),
                                 news_transport=news, clock=lambda: elapsed[0], sleep=pause)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(report['articles']), 2)

    def test_duplicate_url_cannot_bypass_restrictions_or_add_a_publisher(self):
        restricted = self.parse(feed())['articles'][0]
        api_article = {**restricted, 'url': restricted['url'] + '?utm_source=news', 'publisher_name': 'Different label',
                       'collection_sources': ['gnews'], 'investigation_allowed': True, 'content_excerpt': 'API text'}
        for records in [[restricted, api_article], [api_article, restricted]]:
            merged = merge_articles(records)
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]['collection_sources'], ['gnews', 'yahoo-nba'])
            self.assertFalse(merged[0]['investigation_allowed'])
            self.assertIsNone(merged[0]['content_excerpt'])
            self.assertEqual(merged[0]['publisher_name'], 'Yahoo Sports')


if __name__ == '__main__':
    unittest.main()
