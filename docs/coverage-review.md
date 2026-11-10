# Targeted coverage comparison

Checked November 10, 2026. Three GNews searches used one request each, spaced
three seconds apart. All succeeded. No LLM calls or article-page fetches were
made. The local dashboard database was not changed by this experiment.

All searches used the same available window: November 7 at 20:39 UTC through
November 10 at 08:39 UTC. GNews's free-plan 12-hour delay still applies.

| Query | Returned / reported matches | Publisher labels returned | Included event reports after filtering | Largest estimated reporting group count |
| --- | --- | --- | --- | --- |
| `Doncic injury` | 10 / 12 | 6 | 7 | 3 |
| `Thunder Clifford` | 10 / 26 | 5 | 3 | 1 |
| `Thunder Wizards` | 10 / 10 | 8 | 5 | 3 |

Across the three searches, 30 articles carried 13 distinct publisher labels.
Examples include NBC Sports, Bleacher Report, ESPN, Toronto Star, WTOP,
Tulsa World, and Times of India. A returned label is not a verified independent
publisher or proof that the linked article is original reporting. Only the
game query downloaded all matches reported by the API.

## Findings

The game query formed one eligible candidate from five publisher labels.
Toronto Star, WTOP, and Schenectady Gazette were treated as likely copies of
one AP report. Tulsa World and Heavy formed two additional estimated groups.
This repeats the earlier finding that focused searches can discover a wider
publisher pool than a small generic NBA result page.

The injury query formed one eligible candidate under the deterministic rules,
but its results require more review. It mixed questionable status, a later
absence, a return to availability, another player's injury, an award, and a
weekly preview. Their shared player mentions do not establish the same event
or independent corroboration. Award headlines and weekly previews are now
held for review, preventing two obvious false injury classifications.

The trade query mostly returned grades, reactions, prior interest, and a
separate waiver. None formed an eligible corroborated trade cluster. Trade
grades now stay in review. Some opinion headlines and primary-event selection
still need work before automatic trade corroboration is enabled.

These examples are a small convenience sample, not a benchmark of every NBA
story. Comparison files include URL and publisher differences against the
earlier local briefing, but the earlier briefing used a different time window.
Those differences cannot isolate the effect of the query strategy.

## Changes and next decision

The dashboard now states estimated reporting groups, source-link counts, and
publisher-label counts together. It flags coverage below the configured target,
and its Sources panel shows which links count together. Source link labels use
the actual reporting group instead of assuming publisher and URL arrays have
the same order.

Keep automatic targeted collection limited to games for now. The trial shows
that the existing provider can find more publisher labels, so another account
is not the immediate requirement. The next collection expansion should use
reviewed injury and transaction examples to distinguish the primary event,
availability changes, and references to another outlet's reporting. That work
can then support targeted collection for those categories within a fixed budget.

Saved responses, processed candidates, and metrics are in the ignored local
folder `artifacts/coverage-comparison/`. Backend and frontend tests cover the
classification and source-display changes. This trial does not establish rights
to reuse full article text or resolve the source-use limitations documented in
[news-sources.md](news-sources.md).
