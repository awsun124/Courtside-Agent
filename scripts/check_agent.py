"""Check investigation tools on fictional injury coverage and a separate trade rumor."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from courtside.investigation import InvestigationSettings, investigate_briefing
from courtside.llm import ChatProvider
from courtside.ranking import rank_stories
from courtside.stories import process_report


def scenario():
    now = datetime(2026, 11, 9, 12, tzinfo=timezone.utc).isoformat()
    articles = []
    cases = [
        ('alpha', 'Sample: Lakers give Marcus Reed ankle injury update',
         'Fictional NBA report: Lakers guard Marcus Reed will miss two games with an ankle injury.'),
        ('bravo', 'Sample: Marcus Reed sidelined with Lakers ankle injury',
         'Fictional NBA report: Marcus Reed has an ankle injury and remains out for the Lakers.'),
        ('charlie', 'Sample: Lakers could trade Marcus Reed',
         'Fictional NBA rumor: the Lakers could trade Marcus Reed. No transaction is confirmed.'),
    ]
    for publisher, title, text in cases:
        articles.append(dict(title=title, description=text, content_excerpt=text,
            url=f'https://{publisher}.example.com/sample/reed', publisher_name=f'Sample newsroom {publisher}',
            published_at='2026-11-08T12:00:00Z', collected_at=now))
    result = process_report(dict(provider='Sample', mode='sample', articles=articles,
        requested_start='2026-11-06T12:00:00Z', searchable_end='2026-11-09T00:00:00Z',
        generated_at=now, complete_available_results=True, freshness_delay_hours=12))
    briefing = rank_stories(result)
    target = next(story for story in briefing['candidates'] if story['event'] == 'injury')
    briefing['candidates'] = [target]
    briefing['stories'] = [target] if target['eligible'] else []
    return result, briefing


def assess(before, investigated):
    target = investigated['candidates'][0]
    record = target['investigation']
    tools = {item['tool'] for item in record['activity'] if item['status'] == 'ok'}
    summary = target.get('summary')
    citations = summary.get('citations', []) if summary else []
    checks = dict(
        finished=record['status'] == 'complete',
        inspected_related='inspect_related_stories' in tools,
        searched_articles='search_articles' in tools,
        retrieved_evidence='retrieve_material' in tools,
        cited_target=bool(citations) and all(citation['url'] in target['evidence_urls'] for citation in citations),
        scores_unchanged=all(target[field] == before[field] for field in ('score', 'rank', 'breakdown')),
    )
    return dict(passed=all(checks.values()), checks=checks,
        note='Fictional evidence only. This checks tool use and evidence boundaries, not news accuracy or independent reasoning.',
        investigation=investigated['investigation'], target=target)


def run_check(live=False, env_file=Path('.env')):
    result, briefing = scenario()
    before = deepcopy(briefing['candidates'][0])
    settings = InvestigationSettings(provider='openai-compatible' if live else 'rules',
        max_stories=1, max_steps=8, max_steps_per_story=8, max_seconds=20,
        max_llm_calls=5, max_articles_per_story=3, max_input_characters=16000, max_output_tokens=500)
    provider = ChatProvider(settings, env_file) if live else None
    investigated = investigate_briefing(result, briefing, settings=settings, provider=provider)
    return assess(before, investigated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Use the configured LLM with at most five API attempts. Requires explicit server opt-in.')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/agent-check'))
    args = parser.parse_args()
    try:
        report = run_check(args.live, args.env_file)
    except ValueError:
        parser.exit(2, 'Agent check could not start. Check the server-side LLM key, model, URL, and explicit opt-in. No rules fallback was used.\n')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Mode:', 'live LLM with fictional evidence' if args.live else 'offline rules with fictional evidence')
    print('Result:', 'passed' if report['passed'] else 'failed or incomplete')
    print('LLM calls:', report['investigation']['llm_calls'])
    print('Report:', args.output / 'report.json')
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
