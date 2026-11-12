from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from courtside.schedule import collect_daily, daily_times, schedule_status
from courtside.storage import initialize_database


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / "news.db"
        initialize_database(self.database)
        self.now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        self.refresh = Mock()
        self.service = SimpleNamespace(database=self.database, clock=lambda: self.now, refresh=self.refresh)

    def test_before_six_does_not_collect(self):
        self.now = datetime(2026, 11, 11, 10, 59, tzinfo=timezone.utc)
        self.assertFalse(collect_daily(self.service))
        self.refresh.assert_not_called()
        self.assertEqual(schedule_status(self.now)["next_update_at"], "2026-11-11T11:00:00+00:00")

    def test_at_six_collects_seven_days_once_across_restarts_and_workers(self):
        self.now = datetime(2026, 11, 11, 11, tzinfo=timezone.utc)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: collect_daily(self.service), range(2)))
        self.assertEqual(sum(results), 1)
        self.refresh.assert_called_once_with("live", 7, 3)
        self.assertFalse(collect_daily(self.service))
        self.now = datetime(2026, 11, 12, 11, tzinfo=timezone.utc)
        self.assertTrue(collect_daily(self.service))
        self.assertEqual(self.refresh.call_count, 2)

    def test_failure_keeps_daily_claim_and_does_not_retry_every_minute(self):
        self.refresh.side_effect = RuntimeError("Source unavailable")
        with self.assertLogs("courtside.schedule", level="WARNING"):
            self.assertTrue(collect_daily(self.service))
        self.assertFalse(collect_daily(self.service))
        self.assertEqual(self.refresh.call_count, 1)

    def test_existing_todays_collection_is_reused_on_startup(self):
        with patch("courtside.schedule.read_briefings", return_value=[{"as_of": "2026-11-11T11:30:00Z"}]):
            self.assertTrue(collect_daily(self.service))
        self.refresh.assert_not_called()

    def test_eastern_schedule_tracks_daylight_saving_changes(self):
        for now, expected in [
            (datetime(2026, 3, 7, 12, tzinfo=timezone.utc), "2026-03-08T10:00:00+00:00"),
            (datetime(2026, 10, 31, 12, tzinfo=timezone.utc), "2026-11-01T11:00:00+00:00"),
        ]:
            self.assertEqual(daily_times(now)[1].isoformat(), expected)
