import argparse
import json
from pathlib import Path

from .investigation import InvestigationSettings, investigate_briefing
from .llm import ChatProvider
from .stories import parse_date
from scripts.validate_gdelt import canonical_url
from .storage import initialize_database, read_briefings, read_run

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def add_investigations(result, briefing, previous, settings_file=None, env_file=None):
    blocked_urls = {canonical_url(article["url"]) for article in result["articles"]
                    if article.get("investigation_allowed") is False}
    if blocked_urls:
        allowed_articles = {canonical_url(article["url"]): article for article in result["articles"]
                            if canonical_url(article["url"]) not in blocked_urls}

        def permitted_view(story):
            saved = dict(story)
            for field in ("article_urls", "evidence_urls"):
                if field in saved:
                    saved[field] = [url for url in saved[field] if canonical_url(url) in allowed_articles]
            urls = saved.get("article_urls", saved.get("evidence_urls", []))
            if urls:
                saved["title"] = allowed_articles[canonical_url(urls[0])]["title"]
            if "reporting_groups" in saved and isinstance(saved["reporting_groups"], list):
                groups = []
                for group in saved["reporting_groups"]:
                    urls = [url for url in group["evidence_urls"] if canonical_url(url) in allowed_articles]
                    if urls:
                        members = [allowed_articles[canonical_url(url)] for url in urls]
                        groups.append(dict(evidence_urls=urls, publishers=sorted({a["publisher_name"] for a in members}),
                                           first_published_at=min((a["published_at"] for a in members), key=parse_date)))
                saved["reporting_groups"] = groups
            return saved

        permitted_stories = [permitted_view(story) for story in result["stories"]]
        permitted_stories = [story for story in permitted_stories if story["article_urls"]]
        allowed_ids = {story["id"] for story in permitted_stories}
        blocked_ids = {story["id"] for story in result["stories"]} - allowed_ids
        permitted_result = {**result, "articles": list(allowed_articles.values()), "stories": permitted_stories}
        permitted_briefing = {**briefing, "candidates": [permitted_view(story) for story in briefing["candidates"] if story["id"] in allowed_ids],
                             "stories": [permitted_view(story) for story in briefing["stories"] if story["id"] in allowed_ids]}
        permitted_previous = [{**old, "candidates": [story for story in old["candidates"]
                              if story.get("investigation", {}).get("status") != "source_restricted"
                              and not any(canonical_url(url) in blocked_urls for url in story["evidence_urls"])]}
                              for old in previous]
        reviewed_by_id = {}
        if permitted_briefing["candidates"]:
            reviewed = add_investigations(permitted_result, permitted_briefing, permitted_previous, settings_file, env_file)
            status = reviewed["investigation"]
            reviewed_by_id = {story["id"]: story for story in reviewed["candidates"]}
        else:
            status = dict(status="source_restricted", llm_calls=0, steps_used=0)
        briefing["investigation"] = {**status, "restricted_stories": len(blocked_ids)}
        for story in briefing["candidates"] + briefing["stories"]:
            if story["id"] in blocked_ids:
                story["summary"] = None
                story["what_changed"] = None
                story["investigation"] = dict(status="source_restricted", activity=[],
                    decision_summary="Only attributed headlines and source links are available for this story. No source material was sent to the investigator.")
            elif story["id"] in reviewed_by_id:
                reviewed_story = reviewed_by_id[story["id"]]
                for field in ("summary", "what_changed", "investigation"):
                    if field in reviewed_story:
                        story[field] = reviewed_story[field]
                excluded = sum(canonical_url(url) in blocked_urls for url in story["evidence_urls"])
                if excluded and "investigation" in story:
                    story["investigation"]["excluded_source_links"] = excluded
                    note = f"{excluded} source links contributed coverage metadata only and were excluded from this evidence check."
                    uncertainty = story["investigation"].setdefault("uncertainty", [])
                    if note not in uncertainty:
                        uncertainty.append(note)
        return briefing
    provider = None
    try:
        path = Path(settings_file or PROJECT_ROOT / "config/investigation.json")
        settings = InvestigationSettings(**json.loads(path.read_text()))
        settings.validate()
        provider = ChatProvider(settings, env_file or PROJECT_ROOT / ".env") if settings.provider == "openai-compatible" else None
        return investigate_briefing(result, briefing, previous, settings, provider)
    except Exception:
        briefing["investigation"] = dict(status="unavailable", notice="Investigation is disabled or could not finish. Numerical scores are unchanged.",
                                         llm_calls=getattr(provider, "calls_made", 0))
        for candidate in briefing["candidates"] + briefing["stories"]:
            candidate["summary"] = None
            candidate["what_changed"] = None
            candidate["investigation"] = dict(status="unavailable", activity=[], summary=None,
                                              decision_summary="Investigation unavailable. Review the original sources.")
        return briefing


def write_report(briefing, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "investigation.json").write_text(json.dumps(briefing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Courtside-Agent investigation", "", f"Data mode: {briefing.get('data_mode', 'live')}",
             f"Provider: {briefing['investigation'].get('provider', 'unavailable')}",
             f"LLM calls: {briefing['investigation']['llm_calls']}",
             "Numerical ranking is unchanged. Summaries below are attributed API excerpts.", ""]
    for story in briefing["candidates"]:
        investigation = story["investigation"]
        lines.extend([f"## {story['title']}", "", f"Status: {investigation['status']}",
                      investigation["decision_summary"], ""])
        if story.get("summary"):
            lines.append(story["summary"]["text"])
            lines.extend(f"- {citation['publisher']}: {citation['url']}" for citation in story["summary"]["citations"])
        lines.extend(f"- {item['tool']}: {item['decision']}" for item in investigation["activity"])
        lines.extend(f"- {warning}" for warning in investigation.get("uncertainty", []))
        if story.get("what_changed"):
            lines.extend(["", "Previous briefing comparison: " + json.dumps(story["what_changed"])])
        lines.append("")
    (output / "investigation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "artifacts/courtside.db")
    parser.add_argument("--mode", choices=["live", "sample"], default="live")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts/investigation")
    args = parser.parse_args()
    initialize_database(args.database)
    history = read_briefings(args.database, args.mode, limit=4)
    if not history:
        parser.exit(2, "No saved briefing. Run a manual API refresh first.\n")
    briefing = history[0]
    result = read_run(args.database, briefing["processing_run_id"])
    briefing = add_investigations(result, briefing, history[1:])
    write_report(briefing, args.output)
    print(f"Investigation status: {briefing['investigation']['status']}")
    print(f"Report: {args.output / 'investigation.md'}")


if __name__ == "__main__":
    main()
