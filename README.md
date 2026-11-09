# Courtside-Agent

Court Side is an NBA news app in progress. This repository currently contains
scripts for checking news sources. The backend and dashboard come next.

## Setup

You need Python 3.11+ and curl. No Python packages are required yet.

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
python3 -m unittest discover -s tests -v
```

Tests run offline. They cover article dates, duplicate URLs and headlines,
publisher details, request limits, errors, and private key handling.

## Before publishing

Confirm the news provider's plan and content permissions before publishing the
app or adding AI summaries. GNews free access is for noncommercial use.

- [GNews search](https://docs.gnews.io/endpoints/search-endpoint)
- [GNews authentication](https://docs.gnews.io/authentication)
- [GNews article availability](https://docs.gnews.io/article-availability)
- [GNews terms](https://gnews.io/legal/terms-of-service)
- [GDELT API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
