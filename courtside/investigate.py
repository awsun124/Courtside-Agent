"""Run bounded investigations against saved briefings without refreshing news."""
import argparse
import json
from pathlib import Path

from .investigation import InvestigationSettings, investigate_briefing
from .llm import ChatProvider
from scripts.validate_gdelt import canonical_url
from .storage import initialize_database, read_briefings, read_run

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def add_investigations(result, briefing, previous, settings_file=None, env_file=None):
    blocked_urls = {canonical_url(article["url"]) for article in result["articles"]
                    if article.get("investigation_allowed") is False}
    if blocked_urls:
        blocked_ids = {story["id"] for story in result["stories"]
                       if any(canonical_url(url) in blocked_urls for url in story["article_urls"])}
        permitted_result = {**result, "articles": [article for article in result["articles"]
                            if canonical_url(article["url"]) not in blocked_urls],
                            "stories": [story for story in result["stories"] if story["id"] not in blocked_ids]}
        permitted_briefing = {**briefing, "candidates": [story for story in briefing["candidates"] if story["id"] not in blocked_ids],
                             "stories": [story for story in briefing["stories"] if story["id"] not in blocked_ids]}
        permitted_previous = [{**old, "candidates": [story for story in old["candidates"]
                              if story.get("investigation", {}).get("status") != "source_restricted"
                              and not any(canonical_url(url) in blocked_urls for url in story["evidence_urls"])]}
                              for old in previous]
        if permitted_briefing["candidates"]:
            reviewed = add_investigations(permitted_result, permitted_briefing, permitted_previous, settings_file, env_file)
            status = reviewed["investigation"]
        else:
            status = dict(status="source_restricted", llm_calls=0, steps_used=0)
        briefing["investigation"] = {**status, "restricted_stories": len(blocked_ids)}
        for story in briefing["candidates"] + briefing["stories"]:
            if story["id"] in blocked_ids:
                story["summary"] = None
                story["what_changed"] = None
                story["investigation"] = dict(status="source_restricted", activity=[],
                    decision_summary="Feed headlines are shown with attribution. This story was excluded from investigation because source processing permission has not been established.")
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
