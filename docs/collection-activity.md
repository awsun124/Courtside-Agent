# Collection activity

Expand Collection activity in the dashboard sidebar to see what ran for the
saved briefing. It lists the feed snapshot, the broad discovery search, and
up to two targeted injury or game searches. It records skipped searches and their
reasons rather than implying that every refresh searches for an injury.

Each entry includes its source, query where applicable, request count, outcome,
returned result count, additional article URLs, publisher labels, and labels
new to the current collection. Search entries include the requested date window.

## What the counts mean

- Returned results count the rows supplied by the source. Some may be duplicate
  or rejected article records.
- Additional article URLs count valid canonical URLs not already collected
  earlier in this refresh, including URLs discovered through other sources.
- Publisher labels count distinct labels in that entry's valid article records.
  Labels new to the collection exclude labels already found earlier in the refresh.

These counts do not measure new articles since a previous briefing or establish
independent reporting. The existing grouping and ranking rules still decide
which articles support distinct events and which copies count together.

## Storage and failures

Activity is saved in the processing run and briefing JSON snapshots in SQLite.
No schema migration is required. It travels through the existing latest-briefing
API response and remains attached to the same collection timestamp.

Older briefings explicitly say that no activity was recorded. Sample mode says
that no external news requests were made. A skipped request has no results to
report. A failed request and a successful search with zero results remain distinct.
Partial failures preserve successful collection data.

If a refresh fails completely, the previous briefing and its activity stay
visible. The page's last-refresh error describes that failed attempt. Activity
is labeled with its saved collection date so it is not mistaken for the latest
failed attempt.

Only selected fields are recorded for display. Request URLs, headers, API keys,
and raw error text are excluded. Failure notes describe the problem without
copying potentially sensitive provider messages.

## Live check

On November 10, 2026, a full local refresh saved briefing 13 with:

- Yahoo: one request, 50 results and 50 article URLs added.
- GNews discovery for `NBA`: two requests, 20 results and 20 article URLs added.
- Targeted game search for `hawks lakers`: one request, 10 results and eight
  additional article URLs. Nine publisher labels appeared in those results,
  with seven labels new to that collection.

All four requests are accounted for. Activity in the saved processing run
matches the briefing API response. Coverage remains partial. This refresh
selected a game, not an injury. No LLM requests were made.

The ignored local response is `artifacts/collection-activity-check.json`.
Automated tests cover incremental counts, duplicate URLs, publisher labels,
snapshot persistence, failed requests, skipped requests, older briefings, and
sample mode.

## Choosing searches efficiently

The default three-request GNews budget now permits one discovery request and
up to two distinct targeted requests. Larger budgets use the remainder for
discovery. A one-request budget stays discovery-only. Feed requests keep their
existing separate allowance. Unused requests are not spent merely to fill the
budget, and a source failure stops the remaining targeted requests.

The planner prioritizes candidates closest to the configured reporting-group
minimum, then newer coverage. It uses the same publisher, domain, alias, and
copy rules as numerical ranking. Candidates already meeting that minimum are
not targeted. After each search, it rebuilds the groups so a second search is
not spent on a story the first search already corroborated.

The default service reads recent live briefing history from SQLite. A productive
query waits one hour before it is selected again. A failed query, or one that
adds no estimated reporting groups to the selected story, waits six hours. The
latest actual attempt controls the wait. Old activity without group-gain metrics
uses additional article URLs as a compatibility fallback. Sample briefings and
skipped requests do not start cooldowns.

Collection activity shows why a story was selected, its estimated reporting-group
gain, and cooldown skips. This gain measures corroboration of the selected event,
not merely new URLs returned by the query. It remains an estimate and can be
wrong when event grouping or copy detection is wrong. Cooldowns favor breadth
and may postpone checking another update from a single publisher.

A controlled offline replay of two saved discovery seeds and their real saved
GNews responses produced two eligible stories using three simulated requests:
`NBA`, `thunder wizards`, and `luka doncic back injury`. The targeted searches
added two and three estimated reporting groups respectively. This checks the
planner's behavior, not its average live yield or the quality of generic NBA
discovery. The default budget shifts one request from discovery to corroboration,
which can reduce discovery breadth when few eligible seeds exist.

The subsequent live refresh was refused by the app's existing daily limit of
30 source requests. That limit was preserved. No live improvement is claimed
for this planner yet. The replay is saved locally in the ignored
`artifacts/search-planner-replay.json` file.
