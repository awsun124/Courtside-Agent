from contextlib import closing
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx

from courtside.api import create_app
from courtside.investigation import RulesProvider
from courtside.sample_data import sample_report
from courtside.service import NewsService
from courtside.storage import finish_refresh, start_refresh
from scripts.validate_gnews import SourceError

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.database = Path(self.folder.name) / "courtside.db"
        self.env_file = Path(self.folder.name) / ".env"
        self.env_file.write_text("GNEWS_API_KEY=private-test-key\n")
        self.now = NOW
        self.calls = 0
        self.change_report = lambda report: report
        self.app = create_app(database=self.database, env_file=self.env_file,
                              collector=self.collect, clock=lambda: self.now)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.folder.cleanup()

    def collect(self, options, api_key, now):
        self.calls += 1
        saved = sample_report(now, options.days)
        saved.update(provider="GNews", mode="live", attempts=[dict(status="ok", count=len(saved["articles"]))])
        return self.change_report(saved)

    async def refresh(self, **changes):
        return await self.client.post("/api/refresh", json={"mode": "live", "days": 3, "max_requests": 1, **changes})

    async def test_health_and_empty_state_do_not_call_source(self):
        self.assertEqual((await self.client.get("/health")).json(), {"status": "ok"})
        latest = (await self.client.get("/api/briefings/latest")).json()
        self.assertIsNone(latest["briefing"])
        self.assertEqual(latest["status"]["empty_reason"], "no_saved_briefing")
        self.assertEqual(self.calls, 0)

    async def test_scheduled_mode_disables_public_live_refresh_and_reports_schedule(self):
        app = create_app(database=self.database, env_file=self.env_file, collector=self.collect,
                         clock=lambda: self.now, scheduled=True)
        with patch("courtside.api.run_schedule", new=unittest.mock.AsyncMock()):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                    latest = (await client.get("/api/briefings/latest")).json()
                    self.assertTrue(latest["status"]["schedule"]["enabled"])
                    self.assertEqual((await client.post("/api/refresh", json={"mode": "live"})).status_code, 403)
                    sample = await client.post("/api/refresh", json={"mode": "sample"})
                    self.assertEqual(sample.status_code, 200)
                    self.assertIsNone(sample.json()["status"]["schedule"])
        self.assertEqual(self.calls, 0)

    async def test_sample_mode_works_without_key_and_stays_separate(self):
        self.env_file.unlink()
        with patch.dict("os.environ", {}, clear=True):
            response = await self.refresh(mode="sample")
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["briefing"]["data_mode"], "sample")
        self.assertTrue(saved["briefing"]["stories"])
        self.assertIn("fictional", saved["briefing"]["title"])
        self.assertEqual(self.calls, 0)
        self.assertIsNone((await self.client.get("/api/briefings/latest")).json()["briefing"])
        self.assertIsNotNone((await self.client.get("/api/briefings/latest?mode=sample")).json()["briefing"])
        story_id = saved["briefing"]["stories"][0]["id"]
        self.assertEqual((await self.client.get(f"/api/stories/{story_id}")).status_code, 404)
        self.assertEqual((await self.client.get(f"/api/stories/{story_id}?mode=sample")).status_code, 200)

    async def test_sample_ai_requires_its_own_opt_in(self):
        self.env_file.write_text("ENABLE_LLM_CALLS=true\nLLM_API_KEY=fake-key\nLLM_MODEL=test-model\n")
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run") as network:
            response = await self.client.post("/api/sample/investigate", json={})
        self.assertEqual(response.status_code, 503)
        network.assert_not_called()
        self.assertIsNone((await self.client.get("/api/briefings/latest?mode=sample")).json()["briefing"])

    async def test_sample_ai_only_accepts_server_created_fictional_evidence(self):
        self.env_file.write_text("ENABLE_SAMPLE_AI=true\nLLM_API_KEY=fake-key\nLLM_MODEL=test-model\n")
        forbidden = await self.client.post("/api/sample/investigate", json={"mode": "live"})
        self.assertEqual(forbidden.status_code, 422)
        provider = RulesProvider()
        provider.model = "test-model"
        provider.calls_made = 2
        with patch("courtside.api.ChatProvider", return_value=provider):
            response = await self.client.post("/api/sample/investigate", json={})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["data_mode"], "sample")
        self.assertEqual(result["model"], "test-model")
        self.assertTrue(result["passed"])
        self.assertTrue(result["checks"]["scores_unchanged"])
        self.assertTrue(all(".example.com" in item["url"] for item in result["target"]["summary"]["citations"]))
        self.assertEqual(self.calls, 0)
        self.assertIsNone((await self.client.get("/api/briefings/latest?mode=sample")).json()["briefing"])
        with closing(sqlite3.connect(self.database)) as connection:
            saved = connection.execute("SELECT status, requests_used, result_json FROM sample_agent_runs").fetchone()
        self.assertEqual(saved[:2], ("complete", 2))
        self.assertIn('"data_mode": "sample"', saved[2])
        limited = await self.client.post("/api/sample/investigate", json={})
        self.assertEqual(limited.status_code, 429)

    async def test_default_pipeline_saves_feed_only_status_and_respects_source_failure(self):
        from courtside.sources import collect_sources
        from test_feeds import feed
        self.env_file.unlink()
        self.app.state.news.custom_collector = False
        self.app.state.news.collector = lambda options, key, now: collect_sources(options, key, now, feed_transport=lambda *args: feed())
        with patch.dict("os.environ", {}, clear=True):
            response = await self.refresh()
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["refresh"]["requests_used"], 1)
        self.assertEqual(saved["briefing"]["source"], "Monitored sources")
        self.assertEqual(saved["briefing"]["sources"][0]["status"], "unconfigured")
        self.assertEqual(saved["briefing"]["sources"][1]["status"], "ok")
        story = saved["briefing"]["candidates"][0]
        self.assertEqual(story["investigation"]["status"], "source_restricted")
        detail = (await self.client.get(f"/api/stories/{story['id']}")).json()
        self.assertEqual(detail["articles"][0]["collection_sources"], ["yahoo-nba"])
        self.now += timedelta(minutes=30)
        def fail(*args):
            raise SourceError("No source available")
        self.app.state.news.collector = fail
        with patch.dict("os.environ", {}, clear=True):
            failed = await self.refresh()
        self.assertEqual(failed.status_code, 502)
        latest = (await self.client.get("/api/briefings/latest")).json()
        self.assertEqual(latest["briefing"]["briefing_id"], saved["briefing"]["briefing_id"])
        self.assertEqual(latest["status"]["last_attempt"]["status"], "failed")

    async def test_live_refresh_rejects_accidental_sample_fallback(self):
        self.change_report = lambda report: {**report, "mode": "sample", "provider": "Sample"}
        response = await self.refresh()
        self.assertEqual(response.status_code, 502)
        self.assertIsNone((await self.client.get("/api/briefings/latest")).json()["briefing"])

    async def test_unavailable_investigation_does_not_break_ranking(self):
        settings_file = Path(self.folder.name) / "invalid-investigation.json"
        settings_file.write_text('{"provider":"unknown"}')
        self.app.state.news.investigation_file = settings_file
        response = await self.refresh(mode="sample")
        self.assertEqual(response.status_code, 200)
        briefing = response.json()["briefing"]
        self.assertEqual(briefing["investigation"]["status"], "unavailable")
        self.assertEqual(len(briefing["stories"]), 2)
        self.assertTrue(all(story["score"] > 0 for story in briefing["stories"]))

    async def test_live_refresh_serves_cached_reads_and_history(self):
        response = await self.refresh()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["refresh"]["requests_used"], 1)
        latest = (await self.client.get("/api/briefings/latest")).json()
        self.assertEqual(latest["briefing"]["data_mode"], "live")
        self.assertEqual(latest["status"]["state"], "ready")
        history = (await self.client.get("/api/briefings")).json()
        self.assertEqual(len(history["briefings"]), 1)
        self.assertEqual(self.calls, 1)
        self.assertNotIn("private-test-key", json.dumps(latest))
        self.assertNotIn("private-test-key", self.database.read_bytes().decode(errors="ignore"))
        self.assertEqual(latest["briefing"]["investigation"]["llm_calls"], 0)
        story = latest["briefing"]["candidates"][0]
        self.assertTrue(story["summary"]["citations"])
        self.assertTrue(story["investigation"]["activity"])
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM investigations").fetchone()[0], 2)

    async def test_failed_live_source_keeps_previous_briefing(self):
        first = (await self.refresh()).json()["briefing"]
        self.now += timedelta(minutes=30)
        def fail(report):
            return {**report, "articles": [], "complete_available_results": False,
                    "attempts": [dict(status="failed", error="GNews rate limit")]}
        self.change_report = fail
        response = await self.refresh()
        self.assertEqual(response.status_code, 502)
        latest = (await self.client.get("/api/briefings/latest")).json()
        self.assertEqual(latest["briefing"]["briefing_id"], first["briefing_id"])
        self.assertEqual(latest["status"]["last_successful_refresh"], first["as_of"])
        self.assertEqual(latest["status"]["last_attempt"]["status"], "failed")

    async def test_partial_source_results_and_errors_stay_visible(self):
        def partial(report):
            report["attempts"].append(dict(status="failed", error="provider error private-test-key"))
            return report
        self.change_report = partial
        response = await self.refresh(max_requests=2)
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["refresh"]["status"], "partial")
        self.assertTrue(saved["briefing"]["source_errors"])
        self.assertTrue(saved["briefing"]["experimental"])
        self.assertNotIn("private-test-key", response.text)

    async def test_missing_key_does_not_silently_use_sample_data(self):
        self.env_file.unlink()
        with patch.dict("os.environ", {}, clear=True):
            response = await self.refresh()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.calls, 0)
        self.assertIsNone((await self.client.get("/api/briefings/latest")).json()["briefing"])

    async def test_unexpected_errors_do_not_expose_secrets(self):
        def fail(report):
            raise RuntimeError("private-test-key")
        self.change_report = fail
        response = await self.refresh()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private-test-key", response.text)
        self.assertNotIn("private-test-key", (await self.client.get("/api/briefings/latest")).text)

    async def test_collector_error_is_a_source_failure_not_missing_key(self):
        def fail(report):
            raise SourceError("private-test-key")
        self.change_report = fail
        response = await self.refresh()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-test-key", response.text)

    async def test_cooldown_persists_when_service_restarts(self):
        await self.refresh()
        self.app.state.news = NewsService(self.database, self.env_file, collector=self.collect, clock=lambda: self.now)
        response = await self.refresh()
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        self.assertEqual(self.calls, 1)

    async def test_live_refresh_allowed_at_thirty_minute_boundary(self):
        await self.refresh()
        self.now += timedelta(minutes=30, seconds=-1)
        blocked = await self.refresh()
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("30 minutes", blocked.json()["detail"])
        self.assertLessEqual(int(blocked.headers["Retry-After"]), 2)
        self.now += timedelta(seconds=1)
        self.assertEqual((await self.refresh()).status_code, 200)
        self.assertEqual(self.calls, 2)

    async def test_overlapping_refresh_is_rejected(self):
        started, release = threading.Event(), threading.Event()
        def wait(report):
            started.set()
            release.wait(timeout=3)
            return report
        self.change_report = wait
        task = asyncio.create_task(self.refresh())
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            response = await self.refresh()
            self.assertEqual(response.status_code, 409)
        finally:
            release.set()
            response = await task
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, 1)

    async def test_expired_refresh_lease_recovers(self):
        previous = start_refresh(self.database, "live", self.now - timedelta(minutes=31), 1)
        response = await self.refresh()
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM refresh_attempts WHERE id=?", (previous["id"],)).fetchone()[0], "failed")

    async def test_previous_request_totals_do_not_block_refresh_after_cooldown(self):
        previous = start_refresh(self.database, "live", self.now - timedelta(minutes=31), 30)
        finish_refresh(self.database, previous["id"], self.now - timedelta(minutes=30), "failed", 30)
        response = await self.refresh()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, 1)

    async def test_public_backend_configuration_preserves_reads_and_blocks_writes(self):
        with patch.dict("os.environ", {"COURTSIDE_PUBLIC_READ_ONLY": "true", "COURTSIDE_ALLOWED_ORIGINS": "https://courtside.example.com", "COURTSIDE_DATABASE": str(self.database)}):
            app = create_app(env_file=self.env_file, collector=self.collect, clock=lambda: self.now)
        async with app.router.lifespan_context(app):
            self.assertEqual(app.state.news.database, self.database)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                latest = await client.get("/api/briefings/latest", headers={"Origin": "https://courtside.example.com"})
                self.assertTrue(latest.json()["status"]["public_read_only"])
                self.assertEqual(latest.headers["Access-Control-Allow-Origin"], "https://courtside.example.com")
                other = await client.get("/api/stats", headers={"Origin": "https://other.example.com"})
                self.assertNotIn("Access-Control-Allow-Origin", other.headers)
                for path, body in [("/api/refresh", {"mode": "sample"}), ("/api/refresh", {"mode": "live"}), ("/api/sample/investigate", {})]:
                    self.assertEqual((await client.post(path, json=body)).status_code, 403)
        self.assertEqual(self.calls, 0)

    async def test_stats_read_does_not_collect_news(self):
        response = await self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["season"], "2026-27")
        self.assertIsNone(response.json()["players"])
        self.assertEqual(self.calls, 0)

    async def test_shared_briefing_reads_exact_saved_edition_without_collection(self):
        first = (await self.refresh()).json()["briefing"]
        self.now += timedelta(days=1)
        await self.refresh()
        calls = self.calls
        response = await self.client.get(f"/api/briefings/{first['briefing_id']}?mode=live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["briefing_id"], first["briefing_id"])
        self.assertEqual(response.json()["as_of"], first["as_of"])
        self.assertEqual((await self.client.get(f"/api/briefings/{first['briefing_id']}?mode=sample")).status_code, 404)
        self.assertEqual((await self.client.get("/api/briefings/99999")).status_code, 404)
        self.assertEqual(self.calls, calls)

    async def test_stale_state_and_story_sources_use_saved_snapshot(self):
        first = (await self.refresh()).json()["briefing"]
        story_id = first["candidates"][0]["id"]
        self.now += timedelta(hours=7)
        stale = (await self.client.get("/api/briefings/latest")).json()
        self.assertEqual(stale["status"]["state"], "stale")
        self.assertTrue(stale["status"]["stale"])
        self.change_report = lambda report: {**report, "articles": [{**article, "publisher_name": "Changed publisher"} for article in report["articles"]]}
        await self.refresh()
        response = await self.client.get(f"/api/stories/{story_id}?briefing_id={first['briefing_id']}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["articles"])
        self.assertNotEqual(response.json()["articles"][0]["publisher_name"], "Changed publisher")

    async def test_empty_eligible_list_is_not_a_failed_collection(self):
        def single_publisher(report):
            report["articles"] = report["articles"][:1]
            return report
        self.change_report = single_publisher
        response = await self.refresh()
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["status"]["empty_reason"], "no_eligible_stories")
        self.assertEqual(saved["briefing"]["stories"], [])
        self.assertTrue(saved["briefing"]["candidates"])

    async def test_request_validation_and_missing_story(self):
        for body in [{"days": 0}, {"days": 8}, {"max_requests": 6}, {"mode": "unknown"}, {"api_key": "do-not-send-keys"}]:
            response = await self.client.post("/api/refresh", json=body)
            self.assertEqual(response.status_code, 422)
        self.assertEqual((await self.client.get("/api/stories/missing")).status_code, 404)
        self.assertEqual((await self.client.get("/api/briefings?limit=1000")).status_code, 422)
        self.assertEqual(self.calls, 0)

    async def test_database_failure_returns_safe_error(self):
        with patch("courtside.api.read_briefings", side_effect=sqlite3.OperationalError("private details")):
            response = await self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private details", response.text)

    async def test_sample_supports_each_allowed_window(self):
        for days in [1, 3, 7]:
            response = await self.refresh(mode="sample", days=days)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["briefing"]["stories"]), 2)
        self.assertEqual(self.calls, 0)

    async def test_local_frontend_origin_is_allowed(self):
        headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                   "Access-Control-Request-Headers": "content-type"}
        allowed = await self.client.options("/api/refresh", headers=headers)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        headers["Origin"] = "https://unknown.example"
        denied = await self.client.options("/api/refresh", headers=headers)
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
