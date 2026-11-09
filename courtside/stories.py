"""Filter saved articles and group likely reports about the same event."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

from scripts.validate_gdelt import canonical_url

TEAM_NAMES = {
    "hawks": "atlanta hawks", "celtics": "boston celtics", "nets": "brooklyn nets",
    "hornets": "charlotte hornets", "bulls": "chicago bulls", "cavaliers": "cleveland cavaliers",
    "cavs": "cleveland cavaliers", "mavericks": "dallas mavericks", "mavs": "dallas mavericks",
    "nuggets": "denver nuggets", "pistons": "detroit pistons", "warriors": "golden state warriors",
    "rockets": "houston rockets", "pacers": "indiana pacers", "clippers": "los angeles clippers",
    "lakers": "los angeles lakers", "grizzlies": "memphis grizzlies", "heat": "miami heat",
    "bucks": "milwaukee bucks", "timberwolves": "minnesota timberwolves", "pelicans": "new orleans pelicans",
    "knicks": "new york knicks", "thunder": "oklahoma city thunder", "magic": "orlando magic",
    "76ers": "philadelphia 76ers", "sixers": "philadelphia 76ers", "suns": "phoenix suns",
    "blazers": "portland trail blazers", "kings": "sacramento kings", "spurs": "san antonio spurs",
    "raptors": "toronto raptors", "jazz": "utah jazz", "wizards": "washington wizards",
}
AMBIGUOUS_TEAMS = {"heat", "magic", "thunder", "kings", "jazz", "bucks", "nets", "suns", "spurs", "bulls"}
NAME_STOP_WORDS = set("the a an to for and of in on at as by from with nba nfl nhl ncaa ucla november sunday saturday monday tuesday wednesday thursday friday head coach best bets injury update points win loss game report news star does what no one this season national basketball association eastern western conference finals".split())
NAME_STOP_WORDS.update(" ".join(TEAM_NAMES.values()).split())
STOP_WORDS = set("the a an to for and of in on at as by from with is are was were be has have his her their its this that after before more over past out will nba says said latest news update report reports".split())
EVENT_WORDS = {
    "injury": r"\b(injury|injured|surgery|strain|tear|torn|re evaluated|out indefinitely|remains out|ruled out|sidelined)\b",
    "trade": r"\b(trade|traded|trades|acquire|acquired|deal)\b",
    "contract": r"\b(signs|signed|signing|extension|waives|waived|contract)\b",
    "game": r"\b(win|wins|won|victory|defeat|defeats|beat|beats|scored|scores|hold off|past cavs|over cavs)\b",
}
BODY_PARTS = {"knee", "ankle", "hamstring", "thumb", "wrist", "shoulder", "foot", "hand", "back", "elbow", "calf", "hip", "finger"}


def clean_text(text):
    text = unicodedata.normalize("NFKD", text or "")
    return " ".join(re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode().lower()))


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("missing date")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("date is missing its time zone")
    return date.astimezone(timezone.utc)


def find_teams(text, basketball_context=False):
    text = clean_text(text)
    found = set()
    for nickname, full_name in TEAM_NAMES.items():
        if re.search(r"\b" + re.escape(full_name) + r"\b", text):
            found.add(full_name)
        elif (nickname not in AMBIGUOUS_TEAMS or basketball_context) and re.search(r"\b" + nickname + r"\b", text):
            found.add(full_name)
    return sorted(found)


def find_people(text):
    names = set()
    for name in re.findall(r"\b[A-Z][\w'-]+\s+[A-Z][\w'-]+\b", text):
        words = clean_text(name).split()
        if len(words) == 2 and not set(words) & NAME_STOP_WORDS:
            names.add(" ".join(words))
    return sorted(names)


def inspect_article(article):
    title = article["title"]
    description = article.get("description") or ""
    excerpt = article.get("content_excerpt") or ""
    lead = re.split(r"[.!?]\s", description or excerpt, maxsplit=1)[0]
    main_text = title + " " + lead
    title_text = clean_text(title)
    text = clean_text(main_text)
    if re.search(r"\b(prop bets?|best bets?|betting odds|promo code|referral code|prediction odds|predictions odds|sportsbook)\b", text) or "/betting/" in article["url"]:
        return "excluded", "Betting preview or promotion", {}
    if re.search(r"\b(roundup|wrap|expanded glance|conference glance|sports schedule|how to watch)\b", title_text):
        return "review", "Several events or a schedule, not one clear story", {}
    basketball_context = bool(re.search(r"\b(nba|basketball)\b", clean_text(main_text + " " + excerpt)))
    teams = find_teams(main_text, basketball_context)
    if not teams:
        return "review", "No clear NBA team in the headline or opening description", {}
    event = next((kind for kind, pattern in EVENT_WORDS.items() if re.search(pattern, text)), None)
    if event is None:
        return "review", "No clear injury, transaction, or game result in the headline or opening description", {}
    if event == "game":
        teams = find_teams(main_text + " " + excerpt, basketball_context)
        if len(teams) != 2:
            return "review", "Game report needs two clear teams", {}
    features = dict(event=event, teams=teams, people=find_people(main_text),
                    body_parts=sorted(BODY_PARTS & set(text.split())),
                    terms=sorted(set(text.split()) - STOP_WORDS),
                    lead=clean_text(lead), copy_excerpt=clean_text(excerpt or description)[:220],
                    game_scores=sorted({score.replace("–", "-") for score in re.findall(r"\b\d{2,3}[-–]\d{2,3}\b", main_text + " " + excerpt)}),
                    rumor=bool(re.search(r"\b(rumor|rumors|reportedly|could|may|might|linked)\b", title_text)))
    return "included", "Clear NBA event in the headline or opening description", features


def similarity(left, right):
    left_terms, right_terms = set(left), set(right)
    return len(left_terms & right_terms) / max(1, min(len(left_terms), len(right_terms)))


def same_event(left, right):
    first, second = left["features"], right["features"]
    if first["event"] != second["event"]:
        return False
    hours = abs((parse_date(left["published_at"]) - parse_date(right["published_at"])).total_seconds()) / 3600
    if hours > (24 if first["event"] == "game" else 72):
        return False
    if first["event"] == "game":
        if first["game_scores"] and second["game_scores"] and not set(first["game_scores"]) & set(second["game_scores"]):
            return False
        return first["teams"] == second["teams"] and similarity(first["terms"], second["terms"]) >= 0.45
    if not set(first["people"]) & set(second["people"]):
        return False
    if first["body_parts"] and second["body_parts"] and first["body_parts"] != second["body_parts"]:
        return False
    return similarity(first["terms"], second["terms"]) >= 0.55


def likely_copy(left, right):
    if clean_text(left["title"]) == clean_text(right["title"]):
        return True
    first, second = left["features"]["copy_excerpt"], right["features"]["copy_excerpt"]
    return min(len(first), len(second)) >= 100 and SequenceMatcher(None, first, second, autojunk=False).ratio() >= 0.9


def group_articles(articles):
    groups = []
    for article in sorted(articles, key=lambda item: (item["published_at"], item["canonical_url"])):
        for group in groups:
            if all(same_event(article, member) for member in group):
                group.append(article)
                break
        else:
            groups.append([article])
    stories = []
    for group in groups:
        copy_groups = []
        for article in group:
            for copies in copy_groups:
                if all(likely_copy(article, other) for other in copies):
                    copies.append(article)
                    break
            else:
                copy_groups.append([article])
        story_id = hashlib.sha256(group[0]["canonical_url"].encode()).hexdigest()[:16]
        stories.append(dict(id=story_id, title=group[0]["title"], event=group[0]["features"]["event"],
                            first_published_at=group[0]["published_at"], latest_published_at=group[-1]["published_at"],
                            article_urls=[article["canonical_url"] for article in group],
                            publishers=sorted({article["publisher_name"] for article in group}),
                            reporting_groups=min(len(copy_groups), len({article["publisher_name"] for article in group})),
                            likely_copies=[[article["url"] for article in copies] for copies in copy_groups if len(copies) > 1],
                            has_rumor=any(article["features"]["rumor"] for article in group),
                            needs_review=True))
    return stories


def process_report(report):
    mode = report.get("mode")
    provider = "Sample" if mode == "sample" else "GNews"
    if mode not in {"live", "sample"} or report.get("provider") != provider or not isinstance(report.get("articles"), list):
        raise ValueError("Expected a GNews report or explicitly labeled sample data")
    start = parse_date(report["requested_start"])
    end = parse_date(report["searchable_end"])
    if start >= end:
        raise ValueError("Invalid report date range")
    articles, skipped = {}, []
    for original in report["articles"]:
        try:
            if not isinstance(original, dict) or not isinstance(original.get("title"), str) or not original["title"].strip():
                raise ValueError("Missing article title")
            if not isinstance(original.get("publisher_name"), str) or not original["publisher_name"].strip():
                raise ValueError("Missing publisher name")
            for field in ("description", "content_excerpt"):
                if original.get(field) is not None and not isinstance(original[field], str):
                    raise ValueError(f"Invalid {field}")
            canonical = canonical_url(original["url"])
            published = parse_date(original.get("published_at"))
            parse_date(original.get("collected_at"))
            if not start <= published <= end:
                raise ValueError("Publication date outside the available window")
            if canonical in articles:
                skipped.append(dict(url=original["url"], reason="Repeated article URL"))
                continue
            article = {**original, "canonical_url": canonical}
            decision, reason, features = inspect_article(article)
            article.update(decision=decision, decision_reason=reason, features=features)
            articles[canonical] = article
        except (KeyError, ValueError, TypeError) as error:
            skipped.append(dict(reason=str(error)))
    included = [article for article in articles.values() if article["decision"] == "included"]
    return dict(source=provider, mode=mode, input_complete=bool(report.get("complete_available_results")),
                window_start=report["requested_start"], window_end=report["searchable_end"],
                freshness_delay_hours=report.get("freshness_delay_hours", 12),
                collected_at=report["generated_at"], articles=list(articles.values()),
                decisions=dict(Counter(article["decision"] for article in articles.values())),
                skipped_records=skipped, stories=group_articles(included), ranked=False)


def write_report(result, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "stories.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    source_note = "Fictional sample data." if result.get("mode") == "sample" else "Based on saved live GNews results."
    lines = ["# Courtside-Agent story groups", "", source_note + " No new API requests.",
             f"Available window: {result['window_start']} to {result['window_end']}",
             f"Original collection complete: {result['input_complete']}",
             f"Decisions: {result['decisions']}", "",
             "These are story candidates for review, not ranked or verified news.",
             "Matching publisher names and similar wording do not prove independent reporting.",
             "Reporting groups are an estimate after grouping likely copies.", ""]
    for story in result["stories"]:
        lines.extend([f"## {story['title']}", "", f"Event: {story['event']}",
                      f"Articles: {len(story['article_urls'])}, publisher labels: {len(story['publishers'])}, estimated reporting groups: {story['reporting_groups']}",
                      f"Contains a rumor headline: {story['has_rumor']}", ""])
        lines.extend(f"- {url}" for url in story["article_urls"])
        lines.append("")
    lines.extend(["## Excluded articles and articles needing review", ""])
    lines.extend(f"- {article['decision']}: {article['title']} ({article['decision_reason']})"
                 for article in result["articles"] if article["decision"] != "included")
    (output / "stories.md").write_text("\n".join(lines) + "\n")


def main():
    from .storage import save_run
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("artifacts/gnews-validation/report.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/stories"))
    parser.add_argument("--database", type=Path, default=Path("artifacts/courtside.db"))
    args = parser.parse_args()
    try:
        result = process_report(json.loads(args.input.read_text()))
        run_id = save_run(result, args.database)
        result["run_id"] = run_id
        write_report(result, args.output)
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        parser.exit(2, f"Could not process the report: {error}\n")
    print(f"Saved {len(result['stories'])} story candidates. Article decisions: {result['decisions']}")
    print(f"Report: {args.output / 'stories.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
