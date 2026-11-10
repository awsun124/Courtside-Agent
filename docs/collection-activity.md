# Collection activity

Expand Collection activity in the dashboard sidebar to see what ran for the
saved briefing. It lists the feed snapshot, the broad discovery search, and
the targeted injury or game search. It records skipped searches and their
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
