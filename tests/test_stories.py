"""Check article filtering, event grouping, and SQLite history."""
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from courtside.stories import process_report
from courtside.storage import save_run


def article(title, description, url="https://example.com/story", publisher="Example Sports", date="2026-11-08T12:00:00Z"):
    return dict(title=title, description=description, content_excerpt=description,
                url=url, publisher_name=publisher, published_at=date, collected_at="2026-11-09T06:00:00Z")


def report(articles):
    return dict(provider="GNews", mode="live", articles=articles,
                requested_start="2026-11-06T06:00:00Z", requested_end="2026-11-09T06:00:00Z",
                searchable_end="2026-11-08T18:00:00Z", generated_at="2026-11-09T06:00:00Z",
                freshness_delay_hours=12, complete_available_results=False)


def injury(**changes):
    saved = article("Pistons center remains out for two weeks",
                    "The Detroit Pistons shared a Jalen Duren injury update after his hamstring strain.")
    return {**saved, **changes}


class StoryTests(unittest.TestCase):
    def test_betting_preview_is_not_injury_reporting(self):
        saved = article("Lakers vs. Pistons Prediction, Odds and Best NBA Prop Bets",
                        "The Detroit Pistons remain without Jalen Duren because of his hamstring injury.")
        result = process_report(report([saved]))
        self.assertEqual(result["articles"][0]["decision"], "excluded")
        self.assertEqual(result["stories"], [])

    def test_incidental_nba_mention_and_roundup_need_review(self):
        articles = [article("Apple adds thousands of new apps", "New apps include NBA, NHL and Zoom."),
                    article("NBA roundup: Curry and Brunson shine", "The Warriors and Knicks won their games.", url="https://example.com/roundup")]
        result = process_report(report(articles))
        self.assertEqual(result["decisions"], {"review": 2})
        self.assertEqual(result["stories"], [])

    def test_same_player_different_events_stay_separate(self):
        articles = [injury(), article("Jalen Duren signs Pistons extension",
                                     "Jalen Duren signed a new contract with the Detroit Pistons.", url="https://other.com/contract")]
        result = process_report(report(articles))
        self.assertEqual(len(result["stories"]), 2)

    def test_different_players_and_injuries_stay_separate(self):
        other_player = article("Pistons give Cade Cunningham injury update",
                               "Cade Cunningham is out with a hamstring strain for the Detroit Pistons.", url="https://other.com/injury")
        other_injury = injury(title="Jalen Duren has a new knee injury",
                              description="The Detroit Pistons announced a Jalen Duren knee injury.",
                              url="https://third.com/injury")
        result = process_report(report([injury(), other_player, other_injury]))
        self.assertEqual(len(result["stories"]), 3)

    def test_syndicated_copies_preserve_links_without_double_counting(self):
        first = injury()
        second = injury(url="https://other.com/story", publisher_name="Other Sports")
        result = process_report(report([first, second]))
        self.assertEqual(len(result["stories"]), 1)
        story = result["stories"][0]
        self.assertEqual(len(story["publishers"]), 2)
        self.assertEqual(story["reporting_groups"], 1)
        self.assertEqual(len(story["likely_copies"][0]), 2)
        self.assertEqual(result["articles"][0]["url"], first["url"])

    def test_same_game_groups_but_another_opponent_does_not(self):
        articles = [article("Brunson powers Knicks over Cavs", "Jalen Brunson scored 31 points as the New York Knicks beat the Cleveland Cavaliers 109-97."),
                    article("Knicks beat Cavaliers behind Brunson", "Jalen Brunson scored 31 as the New York Knicks beat the Cleveland Cavaliers 109-97.", url="https://other.com/game"),
                    article("Knicks beat Lakers behind Brunson", "Jalen Brunson scored 31 as the New York Knicks beat the Los Angeles Lakers 109-97.", url="https://third.com/game")]
        result = process_report(report(articles))
        self.assertEqual(sorted(len(story["article_urls"]) for story in result["stories"]), [1, 2])

    def test_copied_opening_with_small_edits_counts_once(self):
        opening = "Jalen Brunson scored 31 points to lead the New York Knicks to a convincing 109-97 victory over the Cleveland Cavaliers on Saturday in a rematch of last season's Eastern Conference finals."
        first = article("Brunson powers Knicks over Cavaliers", opening)
        second = article("Knicks beat Cavaliers behind Brunson", opening.replace("on Saturday", "on Nov 7"),
                         url="https://other.com/game", publisher="Other Sports")
        result = process_report(report([first, second]))
        self.assertEqual(len(result["stories"]), 1)
        self.assertEqual(result["stories"][0]["reporting_groups"], 1)

    def test_different_game_scores_do_not_merge(self):
        first = article("Knicks beat Cavaliers", "The New York Knicks beat the Cleveland Cavaliers 109-97.")
        second = article("Knicks beat Cavaliers", "The New York Knicks beat the Cleveland Cavaliers 120-110.", url="https://other.com/game")
        result = process_report(report([first, second]))
        self.assertEqual(len(result["stories"]), 2)

    def test_dates_and_repeated_urls_are_checked_again(self):
        result = process_report(report([injury(), injury(url="https://example.com/story?utm_source=feed"),
                                        injury(url="https://other.com/old", published_at="2026-11-01T12:00:00Z"),
                                        injury(url="https://other.com/future", published_at="2026-11-09T12:00:00Z")]))
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(len(result["skipped_records"]), 3)

    def test_bad_metadata_does_not_discard_good_articles(self):
        result = process_report(report([injury(), injury(url="https://other.com/bad", description=["invalid"])]))
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(len(result["skipped_records"]), 1)
        with self.assertRaises(ValueError):
            process_report({"provider": "unknown", "articles": []})

    def test_partial_input_and_rumors_stay_labeled(self):
        saved = article("Pistons could trade Jalen Duren", "The Detroit Pistons may trade Jalen Duren.")
        result = process_report(report([saved]))
        self.assertFalse(result["input_complete"])
        self.assertFalse(result["ranked"])
        self.assertTrue(result["stories"][0]["has_rumor"])
        self.assertTrue(result["stories"][0]["needs_review"])

    def test_grouping_is_stable_when_input_order_changes(self):
        articles = [injury(), injury(url="https://other.com/story", publisher_name="Other Sports")]
        self.assertEqual(process_report(report(articles))["stories"], process_report(report(list(reversed(articles))))["stories"])

    def test_sqlite_preserves_sources_and_history_without_duplicate_articles(self):
        result = process_report(report([injury()]))
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "courtside.db"
            save_run(result, database)
            save_run(result, database)
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM processing_runs").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM story_clusters").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT original_url, publisher_name FROM articles").fetchone(),
                                 ("https://example.com/story", "Example Sports"))
            broken = deepcopy(result)
            broken["stories"][0]["article_urls"] = ["https://missing.com/article"]
            with self.assertRaises(KeyError):
                save_run(broken, database)
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM processing_runs").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
