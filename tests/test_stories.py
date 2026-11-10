"""Check article filtering, event grouping, and SQLite history."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

from courtside.stories import process_report
from courtside.ranking import rank_stories
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
    def test_reviewed_news_examples(self):
        cases = json.loads((Path(__file__).parent / "fixtures/news_review.json").read_text())
        for case in cases:
            with self.subTest(title=case["title"]):
                result = process_report(report([article(case["title"], case["description"])]))
                self.assertEqual(result["articles"][0]["decision"], case["decision"])

    def test_reviewed_event_examples(self):
        cases = json.loads((Path(__file__).parent / "fixtures/event_review.json").read_text())
        for case in cases:
            with self.subTest(title=case["title"], feed=case.get("feed", False)):
                saved = article(case["title"], case["description"])
                if case.get("feed"):
                    saved.update(collection_sources=["yahoo-nba"], source_url="https://sports.yahoo.com/nba/rss/")
                result = process_report(report([saved]))
                processed = result["articles"][0]
                self.assertEqual(processed["decision"], case["decision"])
                if case.get("event"):
                    self.assertEqual(processed["features"]["event"], case["event"])
                if case.get("rumor"):
                    self.assertTrue(processed["features"]["rumor"])

    def test_feed_context_requires_the_matching_endpoint(self):
        saved = article("Maxey leads Sixers past Bulls", "")
        saved.update(collection_sources=["yahoo-nba"], source_url="https://unrelated.example/feed")
        result = process_report(report([saved]))
        self.assertFalse(result["articles"][0]["nba_context"])
        self.assertEqual(result["articles"][0]["decision"], "review")
        saved["source_url"] = "https://sports.yahoo.com/nba/rss/"
        result = process_report(report([saved]))
        self.assertTrue(result["articles"][0]["nba_context"])
        self.assertEqual(result["articles"][0]["context_basis"], "NBA-specific feed")
        self.assertEqual(result["articles"][0]["decision"], "included")

    def test_host_announcements_require_same_year_and_city_to_group(self):
        articles = [article("Denver to host NBA All-Star Game in 2029", ""),
                    article("Denver reportedly to host NBA All-Star Game in 2029", "", url="https://second.com/host"),
                    article("Denver to host NBA All-Star Game in 2030", "", url="https://third.com/host"),
                    article("Seattle to host NBA All-Star Game in 2029", "", url="https://fourth.com/host")]
        result = process_report(report(articles))
        self.assertEqual(sorted(len(story["article_urls"]) for story in result["stories"]), [1, 1, 2])

    def test_off_court_reports_group_without_merging_other_players_or_events(self):
        titles = ["NBA star Marcus Reed says family safe after alleged stalker arrested at home",
                  "Stalking suspect arrested at NBA player Marcus Reed home",
                  "Stalking suspect arrested at NBA player Jordan Smith home",
                  "Stalking suspect arrested at NBA player Marcus Reed arena",
                  "Lakers sign Marcus Reed to contract extension"]
        articles = [article(title, "", url=f"https://example.com/{index}") for index, title in enumerate(titles)]
        result = process_report(report(articles))
        self.assertEqual(sorted(len(story["article_urls"]) for story in result["stories"]), [1, 1, 1, 2])

    def test_milestones_with_different_stats_do_not_merge(self):
        first = article("Marcus Reed ties NBA record with 12 assists", "")
        second = article("Marcus Reed ties NBA record with 40 points", "", url="https://second.com/record")
        result = process_report(report([first, second]))
        self.assertEqual(len(result["stories"]), 2)

    def test_game_result_is_not_reclassified_by_an_incidental_injury(self):
        saved = article("Lakers beat Pistons 110-102", "The Los Angeles Lakers beat the Detroit Pistons without injured Marcus Reed.")
        result = process_report(report([saved]))
        self.assertEqual(result["articles"][0]["features"]["event"], "game")

    def test_off_court_report_with_multiple_named_people_needs_review(self):
        saved = article("NBA players Marcus Reed and Jordan Smith discuss stalker arrested at home", "")
        result = process_report(report([saved]))
        self.assertEqual(result["articles"][0]["decision"], "review")

    def test_same_off_court_event_outside_time_window_stays_separate(self):
        title = "NBA player Marcus Reed home after alleged stalker arrested"
        first = article(title, "", date="2026-11-04T12:00:00Z")
        second = article(title, "", url="https://second.com/event", date="2026-11-08T12:00:00Z")
        saved = report([first, second])
        saved["requested_start"] = "2026-11-03T06:00:00Z"
        self.assertEqual(len(process_report(saved)["stories"]), 2)

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

    def test_final_score_headlines_group_despite_different_wording_and_score_order(self):
        articles = [article("NBA final score: Spurs blot out Suns, 122-96", ""),
                    article("Phoenix Suns lose as San Antonio Spurs win 96-122 NBA matchup", "",
                            url="https://other.com/game", publisher="Other Sports")]
        result = process_report(report(articles))
        self.assertEqual(result["decisions"], {"included": 2})
        self.assertEqual(len(result["stories"]), 1)
        self.assertEqual(result["stories"][0]["reporting_groups"], 2)

    def test_score_alone_does_not_turn_a_preview_into_a_result(self):
        saved = article("NBA Suns at Spurs preview after a 122-96 meeting", "")
        result = process_report(report([saved]))
        self.assertEqual(result["articles"][0]["decision"], "review")

    def test_same_teams_and_score_on_different_days_stay_separate(self):
        first = article("NBA Suns lost to Spurs 96-122", "", date="2026-11-06T12:00:00Z")
        second = article("NBA final score: Spurs defeat Suns 122-96", "",
                         url="https://other.com/game", date="2026-11-08T12:00:00Z")
        result = process_report(report([first, second]))
        self.assertEqual(len(result["stories"]), 2)

    def test_missing_score_does_not_split_reports_of_the_same_game(self):
        articles = [article("Jalen Brunson leads Knicks past Cavaliers", "The Cleveland Cavaliers had a lead. Jalen Brunson took care of it."),
                    article("Brunson powers Knicks in NBA rematch", "Jalen Brunson scored 31 points as New York Knicks beat Cleveland Cavaliers 109-97.", url="https://second.com/game"),
                    article("Knicks win Cleveland NBA matchup", "Jalen Brunson led New York Knicks to a 109-97 win over Cleveland Cavaliers.", url="https://third.com/game")]
        result = process_report(report(articles))
        self.assertEqual(len(result["stories"]), 1)
        self.assertEqual(len(result["stories"][0]["article_urls"]), 3)

    def test_commentary_and_watch_guides_do_not_corroborate_a_game(self):
        titles = ["Grading Every Knicks Player After 109-97 Win",
                  "5 Winners and 3 Losers From Knicks Game vs Cavaliers",
                  "Where to watch Knicks vs Cavaliers NBA free live stream",
                  "Cavaliers coach explains infamous quote during playoffs loss to Knicks"]
        for title in titles:
            with self.subTest(title=title):
                saved = article(title, "Jalen Brunson scored 31 as New York Knicks beat Cleveland Cavaliers 109-97.")
                self.assertEqual(process_report(report([saved]))['articles'][0]['decision'], 'review')

    def test_award_and_weekly_preview_are_not_injury_corroboration(self):
        articles = [article("Lakers Star Luka Doncic Named NBA Player of the Week Amid Historic Start",
                            "The Lakers announced major NBA news for Luka Doncic following his brief injury absence."),
                    article("Week 4 Look Ahead: Luka Doncic dominates while Kon Knueppel returns to injury report",
                            "Luka Doncic played well for the Lakers despite his back injury.", url="https://second.com/preview"),
                    article("NBA trade grades: Thunder acquire Clifford from Kings",
                            "A closer look at the trade between the Thunder and Kings.", url="https://third.com/grades")]
        result = process_report(report(articles))
        self.assertEqual(result['decisions'], {'review': 3})
        self.assertEqual(result['stories'], [])

    def test_injury_subject_does_not_include_another_player_in_the_lead(self):
        first = article("Lakers Get Quentin Grimes Injury Scare vs Pistons",
                        "The NBA Lakers faced a Quentin Grimes injury scare with Luka Doncic already out because of back tightness.")
        second = article("Luka Doncic injury update for Lakers",
                         "Luka Doncic is out for the NBA Lakers with a back injury.", url="https://other.com/injury")
        result = process_report(report([first, second]))
        grimes = result['articles'][0]['features']
        self.assertEqual(grimes['subjects'], ['quentin grimes'])
        self.assertEqual(grimes['body_parts'], [])
        self.assertEqual(len(result['stories']), 2)

    def test_title_case_and_accents_do_not_hide_the_injury_subject(self):
        first = article("Lakers Receive Unwelcome Luka Doncic Injury News",
                        "Luka Doncic is questionable for the NBA Lakers because of back tightness.")
        second = article("Luka Dončić injury update for Lakers",
                         "Luka Dončić has back tightness for the NBA Lakers.", url="https://other.com/injury")
        result = process_report(report([first, second]))
        for saved in result['articles']:
            self.assertEqual(saved['features']['subjects'], ['luka doncic'])
        self.assertEqual(len(result['stories']), 1)

    def test_waiver_is_not_the_background_trade(self):
        saved = article("Thunder Waive Dalen Terry After Nique Clifford Trade",
                        "The NBA Thunder waived Dalen Terry after acquiring Nique Clifford.")
        features = process_report(report([saved]))['articles'][0]['features']
        self.assertEqual(features['event'], 'contract')
        self.assertEqual(features['transaction_action'], 'waiver')
        self.assertEqual(features['subjects'], ['dalen terry'])

    def test_signing_and_waiver_of_the_same_player_stay_separate(self):
        first = article("Lakers sign Marcus Reed", "The NBA Lakers signed Marcus Reed.")
        second = article("Lakers waive Marcus Reed", "The NBA Lakers waived Marcus Reed.", url="https://other.com/waiver")
        self.assertEqual(len(process_report(report([first, second]))['stories']), 2)

    def test_injury_details_after_a_time_abbreviation_are_not_lost(self):
        saved = article("Luka Doncic injury update for Lakers",
                        "Luka Doncic is questionable for the NBA Lakers game at 6 p.m. because of lower back tightness. Another player has a knee injury.")
        features = process_report(report([saved]))['articles'][0]['features']
        self.assertEqual(features['body_parts'], ['back'])

    def test_hyphenated_player_names_are_recognized(self):
        saved = article("Karl-Anthony Towns injury update for Knicks",
                        "Karl-Anthony Towns has an ankle injury for the NBA Knicks.")
        features = process_report(report([saved]))['articles'][0]['features']
        self.assertEqual(features['subjects'], ['karl anthony towns'])

    def test_signing_action_ignores_a_background_waiver(self):
        saved = article("Lakers Sign Marcus Reed After Bulls Waive Jordan Smith",
                        "The NBA Lakers signed Marcus Reed.")
        features = process_report(report([saved]))['articles'][0]['features']
        self.assertEqual(features['transaction_action'], 'signing')
        self.assertEqual(features['subjects'], ['marcus reed'])

    def test_prior_interest_and_reactions_do_not_corroborate_a_trade(self):
        titles = ["Report: Lakers had interest in Nique Clifford before trade to Thunder",
                  "Why the Nuggets are the Biggest Losers in Thunder Trade for Nique Clifford",
                  "Warriors have no urgency to trade Porzingis, give up draft picks"]
        for title in titles:
            with self.subTest(title=title):
                result = process_report(report([article(title, "A reaction to recent NBA trade news.")]))
                self.assertEqual(result['articles'][0]['decision'], 'review')

    def test_injury_absence_and_return_stay_connected_with_dated_evidence(self):
        articles = [article("Lakers rule Marcus Reed out with ankle injury", "Marcus Reed has an NBA ankle sprain.", date="2026-11-06T12:00:00Z"),
                    article("Marcus Reed remains out for Lakers with ankle sprain", "The NBA Lakers are without Marcus Reed.", url="https://second.com/update", publisher="Second Sports", date="2026-11-07T12:00:00Z"),
                    article("Marcus Reed cleared to play after ankle injury", "Marcus Reed is available for the NBA matchup against the Hawks.", url="https://third.com/return", publisher="Third Sports")]
        result = process_report(report(articles))
        self.assertEqual(len(result['stories']), 1)
        self.assertEqual(result['stories'][0]['title'], articles[-1]['title'])
        story = rank_stories(result)['stories'][0]
        self.assertEqual([update['availability'] for update in story['injury_updates']], ['unavailable', 'unavailable', 'available'])
        self.assertEqual([update['url'] for update in story['injury_updates']], [item['url'] for item in articles])
        self.assertEqual(story['breakdown']['freshness']['points'], 0)

    def test_opposite_sides_and_distant_injury_reports_stay_separate(self):
        first = article("Marcus Reed has left ankle injury for Lakers", "An NBA injury update.", date="2026-11-04T12:00:00Z")
        second = article("Marcus Reed has left ankle injury for Lakers", "An NBA injury update.", url="https://second.com/left")
        third = article("Marcus Reed has right ankle injury for Lakers", "An NBA injury update.", url="https://third.com/right")
        saved = report([first, second, third])
        saved['requested_start'] = '2026-11-03T06:00:00Z'
        self.assertEqual(len(process_report(saved)['stories']), 3)

    def test_restricted_injury_reports_do_not_get_derived_availability_updates(self):
        saved = article("Marcus Reed ruled out for Lakers with ankle injury", "An NBA ankle injury update.")
        saved['investigation_allowed'] = False
        story = rank_stories(process_report(report([saved])))['candidates'][0]
        self.assertEqual(story['injury_updates'], [])

    def test_uncertain_and_negated_availability_are_not_a_confirmed_return(self):
        cases = [('not ruled out', 'uncertain'), ('not yet cleared to play', 'unavailable'),
                 ('not expected to play', 'unavailable'), ('not yet available', 'unavailable'),
                 ('expected to return', 'uncertain'), ('questionable', 'uncertain')]
        for phrase, expected in cases:
            with self.subTest(phrase=phrase):
                saved = article(f"Marcus Reed {phrase} for Lakers after ankle injury", "An NBA ankle injury update.")
                features = process_report(report([saved]))['articles'][0]['features']
                self.assertEqual(features['injury_availability'], expected)

    def test_return_timeline_does_not_establish_availability(self):
        saved = article("Marcus Reed ankle injury return timeline for Lakers", "An NBA injury discussion.")
        features = process_report(report([saved]))['articles'][0]['features']
        self.assertIsNone(features['injury_availability'])

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
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM processing_runs").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM story_clusters").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT original_url, publisher_name FROM articles").fetchone(),
                                 ("https://example.com/story", "Example Sports"))
            broken = deepcopy(result)
            broken["stories"][0]["article_urls"] = ["https://missing.com/article"]
            with self.assertRaises(KeyError):
                save_run(broken, database)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM processing_runs").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
