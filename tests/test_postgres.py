from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
import sqlite3
import unittest
from uuid import uuid4
from urllib.parse import quote
from unittest.mock import patch

from courtside.database import connect, database_setting, is_postgres, migrate_database
from courtside.service import NewsService
from courtside.storage import (finish_sample_agent, read_briefings, read_refreshes,
                               start_refresh, start_sample_agent)
from courtside.schedule import collect_daily
from courtside.stats import read_stats, save_stats


class DatabaseSettingsTests(unittest.TestCase):
    def test_postgres_url_wins_over_local_path(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://example/db', 'COURTSIDE_DATABASE': 'local.db'}):
            self.assertTrue(is_postgres(database_setting()))

    def test_pooled_url_is_rejected_for_migrations(self):
        with self.assertRaises(ValueError):
            migrate_database('postgresql://user:secret@host-pooler.example/db')


@unittest.skipUnless(os.environ.get('COURTSIDE_TEST_DATABASE_URL'), 'Set an isolated PostgreSQL test database')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        base = os.environ['COURTSIDE_TEST_DATABASE_URL']
        self.schema = 'test_' + uuid4().hex
        with closing(connect(base)) as connection:
            connection.execute('CREATE SCHEMA ' + self.schema)
        separator = '&' if '?' in base else '?'
        self.database = base + separator + 'options=' + quote('-csearch_path=' + self.schema)
        self.addCleanup(self.drop_schema, base)
        migrate_database(self.database)
        migrate_database(self.database)

    def drop_schema(self, base):
        with closing(connect(base)) as connection:
            connection.execute('DROP SCHEMA ' + self.schema + ' CASCADE')

    def test_sample_roundtrip_history_and_stats_failure(self):
        service = NewsService(self.database, clock=lambda: datetime(2026, 11, 12, 14, tzinfo=timezone.utc))
        result = service.refresh('sample', 3, 3)
        briefing = result['briefing']
        self.assertGreater(briefing['briefing_id'], 0)
        self.assertTrue(read_briefings(self.database, 'sample'))
        self.assertEqual(read_refreshes(self.database, 'sample')[0]['status'], 'complete')
        self.assertEqual(service.story(briefing['candidates'][0]['id'], 'sample', briefing['briefing_id'])['story']['id'], briefing['candidates'][0]['id'])
        def unavailable(url):
            raise ValueError('Source offline')
        snapshot = save_stats(self.database, '2026-27', service.clock(), transport=unavailable)
        self.assertIsNotNone(snapshot['players']['error'])
        self.assertEqual(read_stats(self.database, '2026-27', service.clock())['players']['rows'], [])

    def test_concurrent_daily_claim_is_shared(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        service = SimpleNamespace(database=self.database,
                                  clock=lambda: datetime(2031, 1, 2, 14, tzinfo=timezone.utc), refresh=Mock())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: collect_daily(service), range(2)))
        self.assertEqual(sum(results), 1)
        service.refresh.assert_called_once()

    def test_refresh_lock_and_sample_agent_lease(self):
        now = datetime(2032, 1, 1, 14, tzinfo=timezone.utc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: start_refresh(self.database, 'live', now, 1), range(2)))
        self.assertEqual(sum('id' in result for result in results), 1)
        self.assertEqual(sum(result.get('status_code') == 409 for result in results), 1)
        job = start_sample_agent(self.database, now)
        self.assertIn('id', job)
        finish_sample_agent(self.database, job['id'], now, 'complete', 1, result={'checked': True})

    def test_transaction_rolls_back_on_failure(self):
        with self.assertRaises(sqlite3.Error):
            with closing(connect(self.database)) as connection, connection:
                connection.execute("INSERT INTO stats_collections VALUES (?, ?)", ('rollback-check', '2026-27'))
                connection.execute('SELECT missing_column FROM stats_collections')
        with closing(connect(self.database)) as connection:
            self.assertIsNone(connection.execute('SELECT season FROM stats_collections WHERE scheduled_at=?', ('rollback-check',)).fetchone())


class ExternalScheduleTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_serves_saved_data_without_starting_collector(self):
        from pathlib import Path
        import tempfile
        import httpx
        from courtside.api import create_app
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            'COURTSIDE_EXTERNAL_SCHEDULE': 'true', 'COURTSIDE_PUBLIC_READ_ONLY': 'true',
        }), patch('courtside.api.run_schedule') as scheduler:
            app = create_app(database=Path(folder) / 'news.db')
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    response = await client.get('/api/briefings/latest')
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()['status']['schedule']['enabled'])
                    self.assertEqual((await client.post('/api/refresh')).status_code, 403)
            scheduler.assert_not_called()


class DailyJobTests(unittest.TestCase):
    def run_job(self, status):
        from unittest.mock import MagicMock
        from scripts import collect_daily as job
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = (status,)
        with patch.object(job, 'NewsService') as service, patch.object(job, 'collect_daily'), \
                patch.object(job, 'collect_stats_daily'), patch.object(job, 'connect', return_value=connection), \
                patch.object(job, 'read_stats', return_value={'players': {'rows': []}, 'teams': {'rows': []}}):
            service.return_value.clock.return_value = datetime(2026, 11, 12, 14, tzinfo=timezone.utc)
            job.main()

    def test_completed_edition_can_be_reused(self):
        self.run_job('complete')

    def test_failed_or_interrupted_edition_fails_the_job(self):
        for status in ('failed', 'running'):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                self.run_job(status)
