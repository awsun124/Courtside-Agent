"""Check ranking scores, evidence requirements, and saved briefing history."""
from contextlib import closing
from copy import deepcopy
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest

from courtside.ranking import RankingSettings, rank_stories
from courtside.storage import save_briefing


def article(publisher, date="2026-11-08T12:00:00Z", title=None):
    return dict(url=f"https://{publisher}.example/report", title=title or f"NBA injury details from {publisher}",
                publisher_name=publisher, decision="included", published_at=date)


def result(articles):
    return dict(window_start="2026-11-06T00:00:00Z", window_end="2026-11-09T00:00:00Z",
                collected_at="2026-11-09T12:00:00Z", input_complete=True, freshness_delay_hours=0,
                articles=articles, stories=[dict(id="story-1", title="NBA injury update", event="injury",
                    article_urls=[saved["url"] for saved in articles], needs_review=False, has_rumor=False)])


def score(articles, settings=None):
    return rank_stories(result(articles), settings)["candidates"][0]


class RankingTests(unittest.TestCase):
    def test_default_weights_and_coverage_normalization(self):
        ranked = score([article("first"), article("second")])
        self.assertEqual(ranked["breakdown"]["coverage"]["score"], 2 / 8)
        self.assertEqual(ranked["breakdown"]["coverage"]["points"], 12.5)
        self.assertAlmostEqual(ranked["score"], sum(item["points"] for item in ranked["breakdown"].values()))
        many = score([article(f"publisher{number}") for number in range(12)])
        self.assertEqual(many["breakdown"]["coverage"]["score"], 1)

    def test_growing_coverage_uses_rates_not_raw_counts(self):
        ranked = score([article("old", "2026-11-06T12:00:00Z"), article("new1"), article("new2")])
        momentum = ranked["breakdown"]["momentum"]
        self.assertAlmostEqual(momentum["earlier_rate"], 1 / 48)
        self.assertAlmostEqual(momentum["recent_rate"], 2 / 24)
        self.assertAlmostEqual(momentum["score"], 0.6)

    def test_equal_rates_and_declining_coverage_have_zero_momentum(self):
        ranked = score([article("old1", "2026-11-06T12:00:00Z"),
                        article("old2", "2026-11-07T12:00:00Z"), article("new")])
        self.assertEqual(ranked["breakdown"]["momentum"]["score"], 0)
        declining = score([article("old", "2026-11-06T12:00:00Z")])
        self.assertEqual(declining["breakdown"]["momentum"]["score"], 0)

    def test_new_sparse_story_is_damped_and_zero_counts_are_safe(self):
        ranked = score([article("one")])
        self.assertAlmostEqual(ranked["breakdown"]["momentum"]["score"], 1 / 3)
        empty = score([])
        self.assertEqual(empty["score"], 0)
        self.assertTrue(math.isfinite(empty["score"]))
        self.assertFalse(empty["eligible"])

    def test_short_window_does_not_invent_a_baseline(self):
        saved = result([article("first"), article("second")])
        saved["window_start"] = "2026-11-08T00:00:00Z"
        ranked = rank_stories(saved)
        self.assertEqual(ranked["candidates"][0]["breakdown"]["momentum"]["score"], 0)
        self.assertTrue(any("too short" in warning for warning in ranked["warnings"]))

    def test_copies_do_not_add_breadth_or_restart_momentum(self):
        original = article("first", "2026-11-06T12:00:00Z", title="Pistons share an injury update")
        copy = article("second", title=original["title"])
        before = score([original])
        after = score([original, copy])
        self.assertEqual(before["score"], after["score"])
        self.assertEqual(after["breakdown"]["coverage"]["raw_publisher_labels"], 2)
        self.assertEqual(after["breakdown"]["coverage"]["independent_publishers"], 1)
        self.assertEqual(after["breakdown"]["momentum"]["recent_reports"], 0)
        self.assertEqual(after["breakdown"]["freshness"]["score"], 0)

    def test_multiple_articles_from_one_publisher_count_once(self):
        first = article("same")
        second = {**article("same", title="A different follow-up headline"), "url": "https://same.example/another"}
        ranked = score([first, second])
        self.assertEqual(ranked["breakdown"]["coverage"]["independent_publishers"], 1)

    def test_matching_descriptions_count_once_despite_different_excerpt_lengths(self):
        opening = "Marcus Reed scored 32 points and the Los Angeles Lakers extended their winning streak to six games with a 124-114 win over the Atlanta Hawks on Monday night."
        first = {**article('first', title='Reed leads Lakers past Hawks'), 'description': opening,
                 'content_excerpt': opening + ' More details followed in the full report.'}
        second = {**article('second', title='Lakers win sixth straight behind Reed'),
                  'description': opening, 'content_excerpt': None}
        ranked = score([first, second])
        self.assertEqual(ranked['breakdown']['coverage']['independent_publishers'], 1)
        self.assertEqual(len(ranked['evidence_urls']), 2)

    def test_short_shared_description_does_not_override_distinct_reporting(self):
        first = {**article('first'), 'description': 'The Lakers won on Monday.'}
        second = {**article('second'), 'description': first['description']}
        self.assertEqual(score([first, second])['breakdown']['coverage']['independent_publishers'], 2)

    def test_known_publisher_aliases_collapse_affiliates(self):
        settings = RankingSettings(publisher_aliases={"first.example": "one newsroom", "second.example": "one newsroom"})
        ranked = score([article("first"), article("second")], settings)
        self.assertEqual(ranked["breakdown"]["coverage"]["independent_publishers"], 1)

    def test_reviewed_development_freshness_has_a_half_life(self):
        saved = result([article("first"), article("second")])
        saved["stories"][0]["developments"] = [dict(reviewed=True, occurred_at="2026-11-08T12:00:00Z",
                                                   evidence_urls=[saved["articles"][0]["url"]])]
        ranked = rank_stories(saved)
        freshness = ranked["candidates"][0]["breakdown"]["freshness"]
        self.assertEqual(freshness["age_hours"], 24)
        self.assertEqual(freshness["score"], 0.5)
        self.assertEqual(freshness["points"], 10)
        self.assertFalse(ranked["experimental"])

    def test_unreviewed_development_does_not_award_freshness(self):
        saved = result([article("first")])
        saved["stories"][0]["developments"] = [dict(reviewed=False, occurred_at="2026-11-08T12:00:00Z")]
        freshness = rank_stories(saved)["candidates"][0]["breakdown"]["freshness"]
        self.assertEqual(freshness["score"], 0)
        self.assertEqual(freshness["status"], "no reviewed development")

    def test_foreign_or_future_development_evidence_is_rejected(self):
        saved = result([article("first")])
        saved["stories"][0]["developments"] = [dict(reviewed=True, occurred_at="2026-11-08T12:00:00Z",
                                                   evidence_urls=["https://unknown.example/article"])]
        with self.assertRaises(ValueError):
            rank_stories(saved)
        saved["stories"][0]["developments"][0].update(occurred_at="2026-11-09T12:00:01Z", evidence_urls=[saved["articles"][0]["url"]])
        with self.assertRaises(ValueError):
            rank_stories(saved)

    def test_missing_dates_are_rejected_and_outside_articles_do_not_count(self):
        ranked = score([article("old", "2026-11-01T12:00:00Z"), article("future", "2026-11-10T12:00:00Z")])
        self.assertEqual(ranked["score"], 0)
        invalid = article("first")
        invalid["published_at"] = None
        with self.assertRaises(ValueError):
            score([invalid, article("second")])

    def test_partial_input_keeps_scores_but_warns_about_missing_coverage(self):
        saved = result([article("first"), article("second")])
        saved.update(input_complete=False, freshness_delay_hours=12)
        ranked = rank_stories(saved)
        self.assertTrue(ranked["experimental"])
        self.assertEqual(len(ranked["stories"]), 1)
        self.assertTrue(any("incomplete" in warning for warning in ranked["warnings"]))
        self.assertTrue(any("12 hours" in warning for warning in ranked["warnings"]))

    def test_single_source_story_is_scored_but_not_selected(self):
        ranked = rank_stories(result([article("one")]))
        self.assertEqual(ranked["stories"], [])
        self.assertIsNone(ranked["candidates"][0]["rank"])
        self.assertTrue(ranked["candidates"][0]["exclusion_reasons"])

    def test_settings_are_configurable_and_invalid_numbers_are_rejected(self):
        settings = RankingSettings(coverage_weight=1, momentum_weight=0, freshness_weight=0, coverage_target=2)
        self.assertEqual(score([article("first"), article("second")], settings)["score"], 100)
        for settings in [RankingSettings(coverage_weight=2), RankingSettings(recent_hours=0),
                         RankingSettings(coverage_target=0), RankingSettings(limit=11),
                         RankingSettings(freshness_weight=float("nan"))]:
            with self.assertRaises(ValueError):
                rank_stories(result([]), settings)

    def test_ties_and_top_ten_are_stable(self):
        saved = result([])
        saved["stories"] = []
        for number in range(12):
            articles = [article(f"source{number}a"), article(f"source{number}b")]
            saved["articles"].extend(articles)
            saved["stories"].append(dict(id=f"story-{number:02}", title=f"Story {number}", event="injury",
                                         article_urls=[item["url"] for item in articles], needs_review=False))
        first = rank_stories(saved)
        saved["stories"].reverse()
        second = rank_stories(saved)
        self.assertEqual(first["stories"], second["stories"])
        self.assertEqual(len(first["stories"]), 10)
        self.assertEqual([story["rank"] for story in first["stories"]], list(range(1, 11)))

    def test_an_article_cannot_fill_two_top_story_slots(self):
        saved = result([article("first")])
        saved["stories"].append({**saved["stories"][0], "id": "another-story"})
        with self.assertRaises(ValueError):
            rank_stories(saved)

    def test_briefings_keep_settings_scores_and_history(self):
        ranked = rank_stories(result([article("first"), article("second")]))
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "courtside.db"
            save_briefing(ranked, database)
            save_briefing(ranked, database)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM briefings").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM story_scores").fetchone()[0], 2)
                self.assertIn('"coverage_weight": 0.5', connection.execute("SELECT briefing_json FROM briefings LIMIT 1").fetchone()[0])
            broken = deepcopy(ranked)
            broken["candidates"].append(broken["candidates"][0])
            with self.assertRaises(sqlite3.IntegrityError):
                save_briefing(broken, database)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM briefings").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
