"""Score story groups with configurable coverage, momentum, and freshness rules."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import timedelta
import json
import math
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from .stories import clean_text, parse_date, likely_copy
from scripts.validate_gdelt import canonical_url


@dataclass
class RankingSettings:
    coverage_weight: float = 0.5
    momentum_weight: float = 0.3
    freshness_weight: float = 0.2
    coverage_target: int = 8
    recent_hours: float = 24
    minimum_baseline_hours: float = 24
    momentum_minimum_reports: int = 3
    freshness_half_life_hours: float = 24
    minimum_publishers: int = 2
    limit: int = 10
    publisher_aliases: dict = field(default_factory=dict)

    def validate(self):
        weights = [self.coverage_weight, self.momentum_weight, self.freshness_weight]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in weights):
            raise ValueError("Ranking weights must be finite, nonnegative numbers")
        if not math.isclose(sum(weights), 1, abs_tol=1e-9):
            raise ValueError("Ranking weights must add up to 1")
        for name in ("coverage_target", "momentum_minimum_reports", "minimum_publishers", "limit"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.limit > 10:
            raise ValueError("The briefing limit cannot exceed 10")
        for name in ("recent_hours", "minimum_baseline_hours", "freshness_half_life_hours"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite, positive number")
        if not isinstance(self.publisher_aliases, dict) or any(
                not isinstance(domain, str) or not isinstance(name, str) or not name.strip()
                for domain, name in self.publisher_aliases.items()):
            raise ValueError("Publisher aliases must map domains to nonempty publisher names")


def copies_match(first, second):
    return likely_copy(first, second)


def reporting_groups(articles):
    groups = []
    for article in sorted(articles, key=lambda item: (item["published_at"], item["canonical_url"])):
        matching = []
        for group in groups:
            if any(article["publisher_id"] == other["publisher_id"] or
                   article["publisher_host"] == other["publisher_host"] or
                   (article.get("reporting_origin") and article["reporting_origin"] == other.get("reporting_origin")) or
                   copies_match(article, other) for other in group):
                matching.append(group)
        combined = [article]
        for group in matching:
            combined.extend(group)
            groups.remove(group)
        groups.append(combined)
    return [dict(first_published_at=min(parse_date(article["published_at"]) for article in group).isoformat(),
                 publishers=sorted({article["publisher_name"] for article in group}),
                 evidence_urls=sorted(article["url"] for article in group)) for group in groups]


def score_story(story, article_index, window_start, window_end, as_of, settings):
    evidence = {}
    for url in story["article_urls"]:
        article = article_index[canonical_url(url)]
        if article.get("decision") != "included":
            continue
        published_at = parse_date(article["published_at"])
        if not window_start <= published_at <= window_end:
            continue
        publisher = article.get("publisher_name")
        if not isinstance(publisher, str) or not publisher.strip():
            raise ValueError("Story evidence is missing a publisher name")
        normalized_url = canonical_url(article["url"])
        domain = urlsplit(normalized_url).hostname
        publisher_id = clean_text(settings.publisher_aliases.get(domain, publisher))
        evidence[normalized_url] = {**article, "canonical_url": normalized_url,
                                    "publisher_host": domain, "publisher_id": publisher_id}
    groups = reporting_groups(list(evidence.values()))
    publisher_count = len(groups)
    coverage = min(1, publisher_count / settings.coverage_target)
    recent_start = max(window_start, window_end - timedelta(hours=settings.recent_hours))
    recent_hours = (window_end - recent_start).total_seconds() / 3600
    baseline_hours = (recent_start - window_start).total_seconds() / 3600
    recent_count = sum(parse_date(group["first_published_at"]) >= recent_start for group in groups)
    baseline_count = len(groups) - recent_count
    recent_rate = recent_count / recent_hours if recent_hours else 0
    baseline_rate = baseline_count / baseline_hours if baseline_hours else 0
    momentum = 0
    momentum_status = "measured"
    if baseline_hours < settings.minimum_baseline_hours:
        momentum_status = "not enough earlier coverage time"
    elif groups:
        rate_total = recent_rate + baseline_rate
        growth = max(0, (recent_rate - baseline_rate) / rate_total) if rate_total else 0
        momentum = growth * min(1, len(groups) / settings.momentum_minimum_reports)
        if len(groups) < settings.momentum_minimum_reports:
            momentum_status = "reduced because coverage is sparse"
    else:
        momentum_status = "no reporting groups"
    developments = []
    for development in story.get("developments", []):
        if development.get("reviewed") is not True:
            continue
        occurred_at = parse_date(development["occurred_at"])
        urls = development.get("evidence_urls", [])
        if not urls or any(canonical_url(url) not in evidence for url in urls):
            raise ValueError("A reviewed development must link to in-window articles from its story")
        if occurred_at > as_of or not any(parse_date(evidence[canonical_url(url)]["published_at"]) >= occurred_at for url in urls):
            raise ValueError("A development cannot be newer than its supporting evidence or the briefing")
        developments.append((occurred_at, urls))
    freshness = 0
    development_time, development_urls, age_hours = None, [], None
    if developments:
        latest, development_urls = max(developments, key=lambda item: item[0])
        development_time = latest.isoformat()
        age_hours = (as_of - latest).total_seconds() / 3600
        freshness = 2 ** (-age_hours / settings.freshness_half_life_hours)
    reasons = []
    if publisher_count < settings.minimum_publishers:
        reasons.append(f"Needs {settings.minimum_publishers} independent publisher groups, found {publisher_count}")
    points = dict(coverage=100 * settings.coverage_weight * coverage,
                  momentum=100 * settings.momentum_weight * momentum,
                  freshness=100 * settings.freshness_weight * freshness)
    injury_updates = []
    if story["event"] == "injury" and not any(article.get("investigation_allowed") is False for article in evidence.values()):
        for article in sorted(evidence.values(), key=lambda item: (parse_date(item["published_at"]), item["canonical_url"])):
            availability = article.get("features", {}).get("injury_availability")
            if availability:
                injury_updates.append(dict(title=article["title"], availability=availability,
                    published_at=article["published_at"], publisher=article["publisher_name"], url=article["url"]))
    return dict(id=story["id"], title=story["title"], event=story["event"], rank=None,
                teams=sorted({team for article in evidence.values() for team in article.get("features", {}).get("teams", [])}),
                score=sum(points.values()), eligible=not reasons, exclusion_reasons=reasons,
                publishers=sorted({article["publisher_name"] for article in evidence.values()}),
                evidence_urls=sorted(article["url"] for article in evidence.values()),
                reporting_groups=groups, injury_updates=injury_updates,
                related_reading=story.get("related_reading", []), has_rumor=bool(story.get("has_rumor")),
                needs_review=bool(story.get("needs_review", True)),
                breakdown=dict(
                    coverage=dict(score=coverage, points=points["coverage"], independent_publishers=publisher_count,
                                  raw_publisher_labels=len({article["publisher_name"] for article in evidence.values()}),
                                  target=settings.coverage_target),
                    momentum=dict(score=momentum, points=points["momentum"], status=momentum_status,
                                  recent_reports=recent_count, earlier_reports=baseline_count,
                                  recent_hours=recent_hours, earlier_hours=baseline_hours,
                                  recent_rate=recent_rate, earlier_rate=baseline_rate,
                                  recent_start=recent_start.isoformat(), window_end=window_end.isoformat()),
                    freshness=dict(score=freshness, points=points["freshness"],
                                   status="reviewed development" if developments else "no reviewed development",
                                   development_at=development_time, age_hours=age_hours, evidence_urls=development_urls)))


def rank_stories(result, settings=None):
    mode = result.get("mode", "live")
    if mode not in {"live", "sample"}:
        raise ValueError("Data mode must be live or sample")
    settings = settings or RankingSettings()
    settings.validate()
    start, end = parse_date(result["window_start"]), parse_date(result["window_end"])
    as_of = parse_date(result["collected_at"])
    if not start < end <= as_of:
        raise ValueError("The coverage window must end after its start and no later than collection time")
    article_index = {}
    for article in result["articles"]:
        url = canonical_url(article["url"])
        if url not in article_index or parse_date(article["published_at"]) < parse_date(article_index[url]["published_at"]):
            article_index[url] = article
    candidates, assigned_urls, story_ids = [], set(), set()
    for story in result["stories"]:
        if story["id"] in story_ids:
            raise ValueError("Story IDs must be unique")
        story_ids.add(story["id"])
        urls = {canonical_url(url) for url in story["article_urls"]}
        if urls & assigned_urls:
            raise ValueError("An article cannot belong to multiple ranked stories")
        if not urls <= article_index.keys():
            raise ValueError("A story references an article that is missing from the input")
        assigned_urls.update(urls)
        candidates.append(score_story(story, article_index, start, end, as_of, settings))
    candidates.sort(key=lambda story: (-story["score"], -story["breakdown"]["coverage"]["independent_publishers"], story["id"]))
    selected = [story for story in candidates if story["eligible"]][:settings.limit]
    for rank, story in enumerate(selected, 1):
        story["rank"] = rank
    warnings = []
    if mode == "sample":
        warnings.append("Sample data is fictional and is only for trying the app.")
    if not result.get("input_complete"):
        warnings.append("The article collection is incomplete. Scores describe only the downloaded sample.")
    if result.get("freshness_delay_hours", 0):
        warnings.append(f"The source excludes the latest {result['freshness_delay_hours']} hours.")
    for source in result.get("sources", []):
        if source.get("delay_hours"):
            warnings.append(f"{source['name']} excludes the latest {source['delay_hours']} hours. Other sources have their own availability.")
        if source.get("kind") == "rss":
            warnings.append(f"{source['name']} is a recent feed snapshot, not a complete archive of this window.")
        if source.get("status") in {"failed", "skipped", "unconfigured"}:
            warnings.append(f"{source['name']}: {source.get('error') or source.get('note') or 'Unavailable'}")
    if any(story["needs_review"] for story in candidates):
        warnings.append("Story groups still need review.")
    if result.get("skipped_records"):
        warnings.append("Some input articles were skipped during processing.")
    if any(story["breakdown"]["momentum"]["status"] == "not enough earlier coverage time" for story in candidates):
        warnings.append("The available window is too short to measure momentum with these settings.")
    if any(story["breakdown"]["freshness"]["status"] == "no reviewed development" for story in candidates):
        warnings.append("Some stories have no reviewed development. Their freshness score is zero.")
    return dict(title="Sample briefing (fictional data)" if mode == "sample" else "Most-covered stories among our monitored sources",
                data_mode=mode, source=result.get("source", "GNews"), experimental=bool(warnings),
                warnings=warnings, as_of=as_of.isoformat(), window_start=start.isoformat(), window_end=end.isoformat(),
                sources=result.get("sources", []), processing_run_id=result.get("run_id"), settings=asdict(settings),
                collection_activity=result.get("collection_activity", []),
                stories=selected, candidates=candidates)


def write_report(briefing, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "ranking.json").write_text(json.dumps(briefing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# " + briefing["title"], "",
             "Status: " + ("Experimental" if briefing["experimental"] else "Reviewed input"),
             f"Scored as of: {briefing['as_of']}",
             f"Coverage window: {briefing['window_start']} to {briefing['window_end']}", ""]
    lines.extend(f"- {warning}" for warning in briefing["warnings"])
    lines.extend(["", f"Eligible stories shown: {len(briefing['stories'])}", "",
                  "Scores below also include candidates with insufficient evidence.", ""])
    for story in briefing["candidates"]:
        breakdown = story["breakdown"]
        label = f"Rank {story['rank']}" if story["rank"] else "Not selected"
        lines.extend([f"## {label}: {story['title']}", "", f"Score: {story['score']:.2f}/100",
                      f"Coverage: {breakdown['coverage']['points']:.2f} points (estimated independent publishers: {breakdown['coverage']['independent_publishers']})",
                      f"Momentum: {breakdown['momentum']['points']:.2f} points ({breakdown['momentum']['status']})",
                      f"Freshness: {breakdown['freshness']['points']:.2f} points ({breakdown['freshness']['status']})",
                      f"Contains a rumor headline: {story['has_rumor']}", ""])
        lines.extend(f"- {reason}" for reason in story["exclusion_reasons"])
        lines.extend(f"- {url}" for url in story["evidence_urls"])
        lines.append("")
    (output / "ranking.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    from .storage import save_briefing
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("artifacts/stories/stories.json"))
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ranking"))
    parser.add_argument("--database", type=Path, default=Path("artifacts/courtside.db"))
    args = parser.parse_args()
    try:
        settings = RankingSettings(**json.loads(args.settings.read_text())) if args.settings else RankingSettings()
        briefing = rank_stories(json.loads(args.input.read_text()), settings)
        briefing["briefing_id"] = save_briefing(briefing, args.database)
        write_report(briefing, args.output)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(2, f"Could not rank stories: {error}\n")
    print(f"Scored {len(briefing['candidates'])} candidates. {len(briefing['stories'])} meet the evidence minimum.")
    print(f"Report: {args.output / 'ranking.md'}")


if __name__ == "__main__":
    main()
