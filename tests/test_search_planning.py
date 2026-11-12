from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from courtside.service import NewsService
from courtside.sources import collect_sources, plan_searches
from scripts.validate_gnews import SourceError

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def article(title, url, publisher="First Sports"):
    return dict(title=title, url=url, publisher_name=publisher,
                published_at="2026-11-09T18:00:00Z", description="A reported NBA event.")


def history(hours, query="pistons lakers", gain=0, status="ok"):
    return dict(as_of=(NOW - timedelta(hours=hours)).isoformat(), data_mode="live", collection_activity=[
        dict(purpose="corroboration", query=query, requests=1, status=status, added_articles=5,
             reporting_groups_added=gain)])


class SearchPlanningTests(unittest.TestCase):
    def seeds(self):
        return [article("Lakers beat Pistons 110-102", "https://first.example/game"),
                article("Marcus Reed ruled out for Knicks with ankle injury", "https://first.example/injury")]

    def test_zero_reporting_gain_waits_even_if_article_urls_were_added(self):
        plans = plan_searches(self.seeds(), NOW - timedelta(hours=12), NOW, [history(2)])
        blocked = next(item for item in plans if item['query'] == 'pistons lakers')
        self.assertIsNotNone(blocked['skip_reason'])
        self.assertTrue(any(item['skip_reason'] is None for item in plans))
        plans = plan_searches(self.seeds(), NOW - timedelta(hours=12), NOW, [history(6)])
        self.assertTrue(all(item['skip_reason'] is None for item in plans))

    def test_latest_productive_search_overrides_an_older_unproductive_search(self):
        plans = plan_searches(self.seeds(), NOW - timedelta(hours=12), NOW, [history(4), history(2, gain=1)])
        self.assertTrue(all(item['skip_reason'] is None for item in plans))
        plans = plan_searches(self.seeds(), NOW - timedelta(hours=12), NOW, [history(.5, gain=1)])
        self.assertIsNotNone(next(item for item in plans if item['query'] == 'pistons lakers')['skip_reason'])

    def test_publisher_aliases_do_not_hide_a_story_needing_corroboration(self):
        first = self.seeds()[0]
        second = article("Pistons lost to Lakers 102-110", "https://second.example/game", "Second label")
        plans = plan_searches([first, second], NOW - timedelta(hours=12), NOW,
                             publisher_aliases={'second.example': 'First Sports'})
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]['reporting_groups'], 1)

    def run_collection(self, fail_target=False, previous=(), unrelated=False, cover_both=False):
        calls = []
        seeds = self.seeds()
        def transport(url, *unused):
            query = parse_qs(urlsplit(url).query)['q'][0]
            calls.append(query)
            if query == 'NBA':
                rows = seeds
            elif fail_target:
                raise SourceError('GNews rate or quota limit reached')
            elif unrelated:
                rows = [article('NBA draft opinion', 'https://other.example/opinion', 'Other Sports')]
            elif cover_both:
                rows = [{**seed, 'url': seed['url'].replace('first.example', 'second.example'),
                         'publisher_name': 'Second Sports',
                         'title': 'Pistons lost to Lakers 102-110' if index == 0 else 'Marcus Reed sidelined for Knicks with ankle sprain'}
                        for index, seed in enumerate(seeds)]
            else:
                seed = seeds[0] if query == 'pistons lakers' else seeds[1]
                rows = [{**seed, 'url': seed['url'].replace('first.example', 'second.example'), 'publisher_name': 'Second Sports',
                         'title': 'Pistons lost to Lakers 102-110' if query == 'pistons lakers' else 'Knicks Marcus Reed sidelined with ankle sprain'}]
            return {'totalArticles': len(rows), 'articles': [dict(title=row['title'], url=row['url'],
                publishedAt=row['published_at'], description=row['description'], source={'name': row['publisher_name']}) for row in rows]}
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'sources.json'
            config.write_text('{"feeds": []}')
            result = collect_sources(Namespace(days=3, query='NBA', max_requests=3, max_seconds=90, timeout=30),
                'test-key', NOW, config, news_transport=transport, sleep=lambda seconds: None, previous_briefings=previous)
        return result, calls

    def test_one_discovery_and_two_distinct_targets_share_three_requests(self):
        result, calls = self.run_collection()
        self.assertEqual(calls[0], 'NBA')
        self.assertEqual(set(calls[1:]), {'pistons lakers', 'marcus reed ankle injury'})
        self.assertEqual(len(result['attempts']), 3)
        targets = [entry for entry in result['collection_activity'] if entry['purpose'] == 'corroboration']
        self.assertEqual([entry['reporting_groups_added'] for entry in targets], [1, 1])

    def test_failed_target_stops_remaining_requests_and_keeps_discovery(self):
        result, calls = self.run_collection(fail_target=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result['articles']), 2)
        self.assertEqual(result['sources'][0]['status'], 'partial')

    def test_replanning_skips_a_second_story_already_corroborated_by_the_first_search(self):
        result, calls = self.run_collection(cover_both=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result['attempts']), 2)

    def test_cooldown_skips_one_story_and_searches_another(self):
        result, calls = self.run_collection(previous=[history(2)])
        self.assertEqual(calls, ['NBA', 'marcus reed ankle injury'])
        self.assertTrue(any(entry['status'] == 'skipped' and entry['query'] == 'pistons lakers'
                            for entry in result['collection_activity']))

    def test_unrelated_new_urls_do_not_count_as_corroboration(self):
        result, _ = self.run_collection(unrelated=True)
        targets = [entry for entry in result['collection_activity'] if entry['purpose'] == 'corroboration']
        self.assertTrue(all(entry['reporting_groups_added'] == 0 for entry in targets))

    def test_service_loads_only_live_history_for_the_default_collector(self):
        with tempfile.TemporaryDirectory() as folder:
            service = NewsService(Path(folder) / 'news.db')
            with patch('courtside.service.read_briefings', return_value=[history(2)]) as read, \
                 patch('courtside.service.collect_sources', return_value={}) as collect:
                service.collect(Namespace(), 'test-key', NOW)
            read.assert_called_once_with(service.database, 'live', limit=50)
            self.assertEqual(collect.call_args.kwargs['previous_briefings'], [history(2)])
