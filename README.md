# Courtside-Agent

Court Side is an NBA news app in progress. This repository contains collection
scripts, story processing, ranking, and a local FastAPI backend.
The backend serves saved briefings and supports manual refreshes.
The dashboard and AI investigation loop come next.

## Setup

You need Python 3.11+ and curl. The collection scripts use the standard library.
Install the API and test dependencies in a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a free [GNews account](https://gnews.io/), verify your email, and add the
key to a local `.env` file using [.env.example](.env.example) as a template:

```dotenv
GNEWS_API_KEY=your_actual_key
```

Git ignores `.env`. Keep the key private. The script reads this file without
executing it and sends the key in an HTTP header. It does not put the key in
URLs, command arguments, or saved reports. An environment variable takes
priority over the `.env` entry.

## Check GNews

```sh
python3 scripts/validate_gnews.py --days 3 --max-requests 3
```

Results are saved in `artifacts/gnews-validation/`:

- `report.md` has a readable summary.
- `report.json` has request details and article data.
- `articles.csv` lets you inspect the articles in a spreadsheet.

The default limits are three requests, ten articles per page, 90 seconds total,
and 30 seconds per request. Errors stop the run without automatic retries.
The free plan excludes the latest 12 hours. The report shows both the requested
period and the period available through the API.

Exit code 0 means the script downloaded all reported matches without rejected
records or repeated URLs. Exit code 2 means results are incomplete, a request
failed, or the key is missing. A successful request does not prove the results
include every NBA story.

The first [GNews test](docs/gnews-evaluation.md) returned 30 articles. We still
need to filter betting previews, check relevance, and group related coverage.
Publisher names and dates come from GNews and have not been checked against the
original pages. Matching headlines suggest duplicates but do not prove that two
articles share the same reporting. The scripts do not fetch publisher article
bodies or use an LLM.

## Check GDELT

GDELT does not need a key, but our [live tests](docs/gdelt-evaluation.md) hit rate
limits and connection timeouts.

```sh
python3 scripts/validate_gdelt.py --days 7
python3 scripts/validate_gdelt.py --days 1 --timeout 45 --connect-timeout 30
```

Results go in `artifacts/gdelt-validation/`. Requests use daily UTC windows.
The defaults allow 14 requests, 180 seconds total, and 20 seconds per request.
A rate limit causes a pause of at least 30 seconds. If a response reaches the
250-article limit, the script tries smaller windows within the remaining request
and time limits. Failed and skipped windows stay visible in the report.

GDELT observation times are stored separately from collection times. Publication
dates and publisher names stay empty when the API cannot provide them. Source
domains do not necessarily represent independent publishers.

## Run tests

```sh
python -m unittest discover -s tests -v
```

Tests run offline. They cover article dates, duplicate URLs and headlines,
publisher details, request limits, errors, and private key handling.

## Start the API

With the virtual environment active:

```sh
python -m uvicorn courtside.api:app --host 127.0.0.1 --port 8000
```

Open [the API docs](http://127.0.0.1:8000/docs) to try the endpoints. Reads use
SQLite without calling a news source. A fresh database returns an explicit empty
state. Existing CLI briefings are available automatically.

Try sample mode without a key:

```sh
curl -X POST http://127.0.0.1:8000/api/refresh \
  -H 'Content-Type: application/json' \
  -d '{"mode":"sample","days":3}'
curl 'http://127.0.0.1:8000/api/briefings/latest?mode=sample'
```

Sample stories are fictional and stay separate from live briefings. Live mode
is the default and needs `GNEWS_API_KEY` on the server. A failed live refresh
never falls back to sample data. Use `{"mode":"live","days":3,"max_requests":3}`
for a bounded live refresh. The API permits one refresh at a time, waits at least
a minute between live refresh starts, and limits itself to 30 source requests
per UTC day. Those counts do not include standalone collection scripts.

The response includes incomplete-source warnings, source delay, the last
successful collection time, the latest refresh attempt, and a stale flag after
six hours. Failed refreshes keep the previous briefing. See [API notes](docs/api.md)
for routes, limits, and the current scope.

## Filter and group saved articles

```sh
python3 -m courtside.stories
```

This reads `artifacts/gnews-validation/report.json` without calling an API.
It saves a readable report in `artifacts/stories/stories.md`, full results in
`artifacts/stories/stories.json`, and articles and processing history in
`artifacts/courtside.db`. These files stay local and are ignored by Git.

Articles are marked `included`, `excluded`, or `review`, with a reason for each
decision. Betting previews are excluded. Roundups, schedules, incidental mentions,
and unclear events stay available for review. The current rules recognize game
results, injuries, trades, and contracts. Other NBA stories may need review too.

Story grouping checks the event type, teams or player names, publication times,
and overlapping words. Game reports also check opponents and reported scores.
Injuries to different body parts stay separate. Every article in a group must
match every other article, which reduces accidental chains of unrelated reports.
Matching headlines or nearly identical opening text are flagged as likely copies.
They remain linked but contribute one estimated reporting group.

These are conservative rules using limited metadata, not verified facts or a
ranking. They can miss related articles and can still merge different updates.
The rules do not resolve publisher ownership or original reporting. Story IDs
are repeatable for the same input but are not yet matched across briefings.
See [story processing notes](docs/story-processing.md) for the current limits.

## Rank story groups

```sh
python3 -m courtside.ranking --settings config/ranking.json
```

Scores use 50 percent coverage, 30 percent momentum, and 20 percent freshness.
Change the weights, periods, evidence minimum, and publisher aliases in
`config/ranking.json`. Results go to `artifacts/ranking/ranking.md` and
`ranking.json`. Briefing history and score breakdowns are saved in SQLite.

The current partial sample is labeled experimental. Likely copies count once,
and the default needs two independent publisher groups to select a story.
All five current candidates fall below that minimum. Their provisional scores
are still shown with explanations. Freshness stays zero until a substantive
development has reviewed evidence. The script never treats a newer copy as a
new development or fills ten slots without enough evidence.

See [ranking methodology](docs/ranking.md) for formulas and limitations.

## Before publishing

Confirm the news provider's plan and content permissions before publishing the
app or adding AI summaries. GNews free access is for noncommercial use.

- [GNews search](https://docs.gnews.io/endpoints/search-endpoint)
- [GNews authentication](https://docs.gnews.io/authentication)
- [GNews article availability](https://docs.gnews.io/article-availability)
- [GNews terms](https://gnews.io/legal/terms-of-service)
- [GDELT API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
