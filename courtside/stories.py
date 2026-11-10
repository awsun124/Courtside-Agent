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
from .feeds import CATALOG

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
NAME_STOP_WORDS.update("rare feat historic milestone all star game first time man claiming security home says claims son matches record records".split())
NAME_STOP_WORDS.update("get major boost ahead announce named receive unwelcome unsettling scoring streak personal tribute biggest losers after before following amid marquee matchup against latest clash scare trade signing waiver".split())
NAME_STOP_WORDS.update("sign signs signed waive waives waived acquire acquires acquired give gives out questionable doubtful return returns ruled sidelined cleared".split())
STOP_WORDS = set("the a an to for and of in on at as by from with is are was were be has have his her their its this that after before more over past out will nba says said latest news update report reports".split())
EVENT_WORDS = {
    "injury": r"\b(injury|injured|surgery|strain|sprain|tightness|tear|torn|re evaluated|out indefinitely|remains out|ruled out|sidelined)\b",
    "trade": r"\b(trade|traded|trades|acquire|acquired|deal)\b",
    "contract": r"\b(sign|signs|signed|signing|extension|waive|waives|waived|contract)\b",
    "game": r"\b(win|wins|won|victory|defeat|defeats|beat|beats|scored|scores|hold off|holds off|past cavs|over cavs)\b|\b(leads?|lifts?)\b.{0,70}\bpast\b",
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
    for name in re.findall(r"(?<![\w'-])(?=([A-Z][\w'-]+\s+[A-Z][\w'-]+)\b)", text):
        words = clean_text(name).split()
        if len(words) >= 2 and not set(words) & NAME_STOP_WORDS:
            names.add(" ".join(words))
    return sorted(names)


def find_event(text):
    matches = [(match.start(), kind) for kind, pattern in EVENT_WORDS.items()
               if (match := re.search(pattern, text))]
    return min(matches)[1] if matches else None


def reported_availability(text):
    if re.search(r"\b(not (?:yet )?available|not (?:yet )?cleared to play|not expected to play)\b", text):
        return "unavailable"
    if re.search(r"\b(questionable|doubtful|game time decision|not (?:yet )?ruled out|not (?:yet )?off the injury report|expected to (?:return|play)|could return|may return|might return|hopes to return)\b", text):
        return "uncertain"
    if re.search(r"\b(unavailable|out|sidelined|will miss|will be without)\b", text):
        return "unavailable"
    if re.search(r"\b(off (?:the )?injury report|cleared to play|available|will play|returns|has returned|will return|back in (?:the )?lineup)\b", text):
        return "available"
    return None


def has_nba_context(article):
    nba_feeds = {"yahoo-nba", "espn-nba", "cbs-nba", "athletic-nba", "guardian-nba", "post-nba"}
    for feed_id in article.get("collection_sources", []):
        if feed_id in nba_feeds and article.get("source_url") == CATALOG[feed_id][1]:
            return True, "NBA-specific feed"
    text = " ".join(article.get(field) or "" for field in ("title", "description", "content_excerpt"))
    return bool(re.search(r"\b(nba|basketball)\b", clean_text(text))), "Article text"


def inspect_article(article):
    title = article["title"]
    description = article.get("description") or ""
    excerpt = article.get("content_excerpt") or ""
    lead = re.split(r"(?<!\b[A-Za-z])[.!?]\s", description or excerpt, maxsplit=1)[0]
    main_text = title + " " + lead
    title_text = clean_text(title)
    text = clean_text(main_text)
    if re.search(r"\b(prop bets?|best bets?|betting odds|promo code|referral code|prediction odds|predictions odds|sportsbook)\b", text) or "/betting/" in article["url"]:
        return "excluded", "Betting preview or promotion", {}
    if re.search(r"\b(relive|on this day|look back|rewind|flashback)\b", title_text):
        return "review", "Historical retrospective, not evidence of a recent event", {}
    if re.search(r"\b(and more|a lot more)\b", text):
        return "review", "Several topics, not one clear story", {}
    if re.search(r"\b(roundup|wrap|expanded glance|conference glance|sports schedule|how to watch|where to watch)\b", title_text):
        return "review", "Several events or a schedule, not one clear story", {}
    basketball_context, context_basis = has_nba_context(article)
    if re.search(r"\b(fantasy|waiver wire|power rankings|player grades|trade grades|grading every|winners and (?:\d+ )?losers|report card|preview|look ahead|lookahead|open thread|weekly recap|week in review|takeaways|observations after|survey|predictions)\b", title_text):
        return "review", "Fantasy, preview, opinion, or recap rather than a direct event report", {}
    if re.search(r"\bplayer of the (week|month|year)\b", title_text):
        return "review", "Award announcement needs separate event classification", {}
    if re.search(r"\b(best|worst)\b.{0,50}\b(player|team|contract)\b", title_text):
        return "review", "Player or team evaluation, not a reported transaction", {}
    if re.search(r"\b(impressed|applaud|praise)\b", title_text):
        return "review", "Reaction or commentary rather than direct event reporting", {}
    if re.search(r"\bexplains\b.*\bquote\b", title_text):
        return "review", "Reaction or commentary rather than direct event reporting", {}
    if re.search(r"\b(biggest (winners|losers)|salary cap repercussions|silver lining|had interest|previously interested|no urgency to trade)\b", title_text):
        return "review", "Transaction analysis or prior interest, not a new reported move", {}
    if re.search(r"\binjury report\b", title_text) and re.search(r"\b(game|vs|at|starters)\b", title_text):
        return "review", "Pregame availability list rather than one clear injury development", {}
    teams = find_teams(main_text, basketball_context)
    if re.search(r"^(should|could|would|can|what if)\b", title_text):
        return "review", "Question or speculation rather than a specific reported development", {}
    if re.search(r"\b(endorsement|shoe deal|sponsorship)\b", text):
        return "review", "Commercial partnership, not a player roster transaction", {}
    headline_people = find_people(title)
    lead_people = find_people(lead)
    people = sorted(set(headline_people) | set(lead_people))
    primary_title = re.split(r"\b(after|before|following|amid)\b", title, maxsplit=1, flags=re.IGNORECASE)[0]
    subjects = find_people(primary_title) or headline_people or lead_people
    event_key = None
    if basketball_context and re.search(r"\bhost\b.*\bnba all star game\b", title_text):
        year = re.search(r"\b20\d{2}\b", title_text)
        city = re.match(r"([A-Z][a-z]+(?: [A-Z][a-z]+)?) (?:reportedly )?to host", title)
        if year and city:
            event_key = "all-star-host:" + year.group() + ":" + clean_text(city.group(1))
            event = "league"
        else:
            return "review", "Host announcement needs a clear city and event year", {}
    elif basketball_context and len(people) == 1 and re.search(r"\b(arrest|arrested)\b", text) and re.search(r"\b(stalker|stalking|trespass|trespassing)\b", text):
        location = "home" if re.search(r"\b(home|house|residence)\b", text) else "arena" if re.search(r"\b(arena|stadium)\b", text) else "unspecified"
        event, event_key = "off_court", "arrest:stalking:" + location
    elif basketball_context and people and re.search(r"\b(matches|tied|ties|breaks|passes)\b", title_text) and re.search(r"\b(record|feat|milestone)\b", title_text):
        event = "milestone"
        numbers = sorted(set(re.findall(r"\b\d+\b", text)))
        event_key = "milestone:" + ",".join(numbers) if numbers else None
    else:
        injured = re.search(r"\binjured\b", title_text)
        injury_is_description = bool(injured and (
            title_text.startswith("injured ") or any(
                person in title_text and injured.start() < title_text.index(person) for person in subjects)))
        event_title = re.sub(r"\binjured\b", "", title_text) if injury_is_description else title_text
        event = find_event(event_title)
        if event is None and injury_is_description:
            if reported_availability(clean_text(primary_title)):
                event = "injury"
            else:
                return "review", "Injury describes the player, not a reported injury development", {}
        if event is None:
            event = find_event(clean_text(lead))
        if event is None and basketball_context and len(teams) == 2:
            has_score = re.search(r"\b\d{2,3}[-–]\d{2,3}\b", main_text)
            has_result = re.search(r"\b(final score|loses|lost|routs?|humiliate[sd]?|blot out|blots out)\b", title_text)
            if has_score and has_result:
                event = "game"
    if event is None:
        return "review", "No specific supported event in the headline or opening description", {}
    if not teams and event not in {"league", "off_court", "milestone"}:
        return "review", "No clear NBA team in the headline or opening description", {}
    if event == "injury" and re.search(r"\b(questions whether|injury problems|offseason workouts|injury trends)\b", text) and not BODY_PARTS & set(text.split()):
        return "review", "General injury discussion without a specific injury development", {}
    if event == "injury" and len(subjects) > 1:
        return "review", "Multiple possible injury subjects need review", {}
    injury_text = text
    if event == "injury" and subjects:
        lead_text = clean_text(lead)
        other_people = [lead_text.index(person) for person in lead_people if person not in subjects and person in lead_text]
        if other_people:
            injury_text = title_text + " " + lead_text[:min(other_people)]
    injury_availability = None
    injury_sides = []
    if event == "injury":
        injury_availability = reported_availability(clean_text(primary_title)) or reported_availability(injury_text)
        injury_sides = sorted({match.group(1) for match in re.finditer(
            r"\b(left|right)\s+(?:lower\s+|upper\s+)?(?:" + "|".join(sorted(BODY_PARTS)) + r")\b", injury_text)})
    transaction_action = None
    if event == "contract":
        primary_text = clean_text(primary_title)
        if re.search(r"\bwaiv(e|es|ed)\b", primary_text):
            transaction_action = "waiver"
        elif "extension" in primary_text:
            transaction_action = "extension"
        elif re.search(r"\bsign(s|ed|ing)?\b", primary_text):
            transaction_action = "signing"
    if event == "game":
        teams = find_teams(main_text + " " + excerpt, basketball_context)
        if len(teams) != 2:
            return "review", "Game report needs two clear teams", {}
    features = dict(event=event, teams=teams, people=people, subjects=subjects, transaction_action=transaction_action,
                    injury_availability=injury_availability, injury_sides=injury_sides,
                    event_key=event_key, context_basis=context_basis,
                    body_parts=sorted(BODY_PARTS & set(injury_text.split())),
                    terms=sorted(set(text.split()) - STOP_WORDS),
                    lead=clean_text(lead), copy_excerpt=clean_text(excerpt or description)[:220],
                    game_scores=sorted({score.replace("–", "-") for score in re.findall(r"\b\d{2,3}[-–]\d{2,3}\b", main_text + " " + excerpt)}),
                    rumor=bool(re.search(r"\b(rumor|rumors|reportedly|alleged|could|may|might|linked)\b", title_text)))
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
    if first["event"] == "league":
        return bool(first.get("event_key") and first.get("event_key") == second.get("event_key"))
    if first["event"] in {"off_court", "milestone"}:
        if not first.get("people") or not second.get("people") or first["people"][0] != second["people"][0]:
            return False
        same_key = bool(first.get("event_key") and first.get("event_key") == second.get("event_key"))
        if first["event"] == "off_court" and first.get("event_key") != "arrest:stalking:unspecified":
            return same_key
        return same_key and similarity(first["terms"], second["terms"]) >= 0.55
    if first["event"] == "game":
        if first["teams"] != second["teams"]:
            return False
        if first["game_scores"] and second["game_scores"]:
            first_scores = {tuple(sorted(map(int, score.split("-")))) for score in first["game_scores"]}
            second_scores = {tuple(sorted(map(int, score.split("-")))) for score in second["game_scores"]}
            return bool(first_scores & second_scores)
        return bool(set(first["people"]) & set(second["people"])) or similarity(first["terms"], second["terms"]) >= 0.45
    if not set(first.get("subjects", first["people"])) & set(second.get("subjects", second["people"])):
        return False
    if first["event"] == "injury":
        if first.get("injury_sides") and second.get("injury_sides") and first["injury_sides"] != second["injury_sides"]:
            return False
        if first["body_parts"] and second["body_parts"]:
            return first["body_parts"] == second["body_parts"]
        if not set(first["teams"]) & set(second["teams"]):
            return False
    if first["event"] == "contract":
        first_action, second_action = first.get("transaction_action"), second.get("transaction_action")
        if first_action and second_action and first_action != second_action:
            return False
    if first["body_parts"] and second["body_parts"] and first["body_parts"] != second["body_parts"]:
        return False
    return similarity(first["terms"], second["terms"]) >= 0.55


def likely_copy(left, right):
    if clean_text(left["title"]) == clean_text(right["title"]):
        return True
    first_openings = {clean_text(left.get(field))[:220] for field in ("description", "content_excerpt")}
    second_openings = {clean_text(right.get(field))[:220] for field in ("description", "content_excerpt")}
    return any(min(len(first), len(second)) >= 100 and
               SequenceMatcher(None, first, second, autojunk=False).ratio() >= 0.9
               for first in first_openings for second in second_openings)


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
        title_article = group[0]
        if group[0]["features"]["event"] == "injury":
            updates = [article for article in group if article["features"].get("injury_availability")]
            title_article = updates[-1] if updates else group[-1]
        stories.append(dict(id=story_id, title=title_article["title"], event=group[0]["features"]["event"],
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
    provider = report.get("provider")
    allowed = {"Sample"} if mode == "sample" else {"GNews", "Monitored sources"}
    if mode not in {"live", "sample"} or provider not in allowed or not isinstance(report.get("articles"), list):
        raise ValueError("Expected a supported live report or explicitly labeled sample data")
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
            article["nba_context"], article["context_basis"] = has_nba_context(article)
            decision, reason, features = inspect_article(article)
            article.update(decision=decision, decision_reason=reason, features=features)
            articles[canonical] = article
        except (KeyError, ValueError, TypeError) as error:
            skipped.append(dict(reason=str(error)))
    included = [article for article in articles.values() if article["decision"] == "included"]
    return dict(source=provider, mode=mode, input_complete=bool(report.get("complete_available_results")),
                window_start=report["requested_start"], window_end=report["searchable_end"],
                freshness_delay_hours=report.get("freshness_delay_hours", 12),
                sources=report.get("sources", []), collected_at=report["generated_at"], articles=list(articles.values()),
                collection_activity=report.get("collection_activity", []),
                decisions=dict(Counter(article["decision"] for article in articles.values())),
                skipped_records=skipped, stories=group_articles(included), ranked=False)


def write_report(result, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "stories.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    source_note = "Fictional sample data." if result.get("mode") == "sample" else "Based on saved monitored-source results."
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
