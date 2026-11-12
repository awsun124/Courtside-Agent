"""Check NBA statistics parsing, caching, and failure isolation offline."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from courtside.stats import parse_players, parse_teams, read_stats, save_stats, collect_stats_daily, season_for
from courtside.storage import initialize_database

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


def players_payload():
    return dict(parameters=dict(Season="2026-27", SeasonType="Regular Season", PerMode="PerGame"),
                resultSet=dict(headers=["PLAYER_ID", "PLAYER", "TEAM", "GP", "PTS", "REB", "AST", "STL", "BLK"],
                               rowSet=[[1, "Test Player", "BOS", 10, 25, 8, 7, 1, 0.5]]))


def teams_payload():
    children = []
    for offset, conference in ((0, "Eastern Conference"), (15, "Western Conference")):
        entries = [dict(team=dict(id=str(index + 1), displayName=f"Test Team {index}"),
                        stats=[dict(name=name, value=value) for name, value in dict(wins=0, losses=0, avgPointsFor=110, avgPointsAgainst=108).items()])
                   for index in range(offset, offset + 15)]
        children.append(dict(name=conference, standings=dict(season=2027, seasonType=2, entries=entries)))
    return dict(abbreviation="NBA", season=dict(year=2027), children=children)


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / "stats.db"
        initialize_database(self.database)

    def test_player_metrics_and_both_dataset_shapes(self):
        payload = players_payload()
        player = parse_players(payload, "2026-27")[0]
        self.assertEqual((player["name"], player["pts"], player["games"]), ("Test Player", 25, 10))
        payload["resultSets"] = [payload.pop("resultSet")]
        self.assertEqual(parse_players(payload, "2026-27")[0], player)

    def test_wrong_season_totals_missing_and_invalid_numbers_are_rejected(self):
        for mutate in [lambda p: p["parameters"].update(Season="2025-26"),
                       lambda p: p["parameters"].update(PerMode="Totals"),
                       lambda p: p["resultSet"]["rowSet"][0].__setitem__(4, float("nan")),
                       lambda p: p["resultSet"]["rowSet"][0].__setitem__(4, -1),
                       lambda p: p["resultSet"]["rowSet"].append(p["resultSet"]["rowSet"][0])]:
            payload = players_payload()
            mutate(payload)
            with self.assertRaises(ValueError):
                parse_players(payload, "2026-27")

    def test_team_zero_games_and_complete_coverage(self):
        payload = teams_payload()
        teams = parse_teams(payload, "2026-27")
        self.assertEqual(len(teams), 30)
        self.assertEqual(teams[0]["win_percentage"], 0)
        payload["children"][0]["standings"]["entries"].pop()
        with self.assertRaises(ValueError):
            parse_teams(payload, "2026-27")

    def test_team_season_phase_duplicates_and_metrics_are_validated(self):
        for mutate in [lambda p: p["season"].update(year=2026),
                       lambda p: p["children"][0]["standings"].update(seasonType=1),
                       lambda p: p["children"][0]["standings"]["entries"][0]["team"].update(id="2"),
                       lambda p: p["children"][0]["standings"]["entries"][0]["stats"][0].update(value=-1)]:
            payload = teams_payload()
            mutate(payload)
            with self.assertRaises(ValueError):
                parse_teams(payload, "2026-27")
        rows = parse_teams(teams_payload(), "2026-27")
        self.assertEqual(rows[0]["points_per_game"], 110)
        self.assertEqual(rows[0]["points_allowed"], 108)
        self.assertEqual(rows[0]["point_difference"], 2)

    def test_successful_sources_have_independent_attribution(self):
        result = save_stats(self.database, "2026-27", NOW,
                            lambda url: players_payload() if "leagueleaders" in url else teams_payload())
        self.assertEqual(result["players"]["source_name"], "NBA.com")
        self.assertEqual(result["teams"]["source_name"], "ESPN")
        self.assertIn("season=2027", result["teams"]["source_url"])
        self.assertEqual(len(result["teams"]["rows"]), 30)

    def test_failed_team_source_does_not_discard_player_data_and_stale_cache_survives(self):
        def transport(url):
            if "leagueleaders" in url:
                return players_payload()
            raise ValueError("Unavailable")
        first = save_stats(self.database, "2026-27", NOW, transport)
        self.assertEqual(len(first["players"]["rows"]), 1)
        self.assertFalse(first["teams"]["rows"])
        def fail(url):
            raise ValueError("Unavailable")
        save_stats(self.database, "2026-27", NOW + timedelta(days=2), fail)
        cached = read_stats(self.database, "2026-27", NOW + timedelta(days=2))
        self.assertEqual(cached["players"]["collected_at"], NOW.isoformat())
        self.assertTrue(cached["players"]["stale"])
        self.assertTrue(cached["players"]["error"])
        self.assertIsNone(read_stats(self.database, "2027-28", NOW)["players"])

    def test_daily_claim_prevents_repeated_requests(self):
        from unittest.mock import patch
        with patch("courtside.stats.save_stats") as save:
            self.assertTrue(collect_stats_daily(self.database, NOW))
            self.assertFalse(collect_stats_daily(self.database, NOW))
            save.assert_called_once()
        self.assertEqual(season_for(datetime(2027, 1, 1, tzinfo=timezone.utc)), "2026-27")
