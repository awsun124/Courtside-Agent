# Courtside-Agent

Court Side is the application's display name; Courtside-Agent is this repository.

Currently: GDELT and GNews source evaluation scripts, not the application.

## GNews evaluation

Create a free [GNews account](https://gnews.io/), verify your email, and put your
key in the repository's local `.env` file:

```dotenv
GNEWS_API_KEY=your_actual_key
```

`.env` is ignored by Git. `.env.example` contains only the variable name.
Environment variables take precedence over the local file. The file is parsed
as data and never executed. Keys are sent in the supported `X-Api-Key` header,
through curl's standard input, not in command arguments, URLs, or reports.

```sh
python3 scripts/validate_gnews.py --days 3 --max-requests 3
```

Exports go to `artifacts/gnews-validation/`. The default budget is three requests,
ten articles per page, 90 seconds total, and 30 seconds per request. There are no
automatic retries after errors or rate limits. An exhausted request budget is
marked partial even if some articles were returned. Exit 0 means all reported
matches in the accessible window were retrieved without rejected or repeated URL
records. Exit 2 means partial results, an API error, or a missing key.

The free plan excludes the latest 12 hours, so a three-day request covers the
period from three days ago through 12 hours ago. The report labels this gap and
keeps requested and searchable end dates separate. Publisher names, excerpts,
and publication dates are provider-supplied, not independently verified.
Title triage and duplicate headline groups are review hints, not a story ranking.
The script never fetches article bodies from publishers or calls an LLM.

GNews free access is for noncommercial evaluation. Before public deployment,
confirm the intended use, content permissions, and plan requirements.
[Authentication](https://docs.gnews.io/authentication),
[search parameters](https://docs.gnews.io/endpoints/search-endpoint),
[article availability](https://docs.gnews.io/article-availability),
[terms](https://gnews.io/legal/terms-of-service).

## GDELT evaluation

Requires Python 3.11+ and `curl`. No Python packages, API keys, or LLM needed.
TLS verification remains enabled; curl uses the system certificate setup.

```sh
python3 scripts/validate_gdelt.py --days 7
python3 -m unittest discover -s tests -v
```

Exports: `artifacts/gdelt-validation/report.json`, `articles.csv`, and `report.md`
(ignored by Git). Exit 0 means all query windows returned valid uncapped results;
exit 2 means partial results, failures, or rejected records. Neither establishes
exhaustive NBA coverage or validates the articles' claims.

```sh
python3 scripts/validate_gdelt.py --days 1 --max-seconds 90
python3 scripts/validate_gdelt.py --days 3 --window-hours 12 --max-requests 20 --max-seconds 240
python3 scripts/validate_gdelt.py --days 7 --query 'NBA sourcelang:english domainis:espn.com'
```

Defaults: daily UTC windows, 250 results per response, 14 HTTP attempts, 180
seconds total, 20 seconds per request and connection, one retry per window, and at least six
seconds between requests. `--connect-timeout` controls DNS, TCP, and TLS setup
within the overall `--timeout`. Rate-limit responses trigger at least 30 seconds
of cooldown even when moving to another window. Retries use increasing delays. HTTP-200 rate-limit
text is a failure, never an empty success. Capped windows are split and queued
after initial daily windows, subject to the same budgets and a 15-minute minimum.
Failed, capped, split, and unattempted windows appear in the report.

The script measures canonical URL duplicates, possible syndicated headline
groups, source hosts, observed UTC dates, and missing metadata. A title-only
heuristic marks explicit NBA/team cues as `candidate`, obvious promotions as
`excluded`, and the remainder as `uncertain`. These are manual review hints,
not measured relevance, event clustering, or a story ranking. All categories
remain in the exports. Differently worded syndication will be missed, while
matching headlines do not prove syndication. Source hosts are not necessarily
independent publishers. Original URLs and GDELT domain labels are retained.

`gdelt_seen_at`, `published_at`, and `collected_at` are separate fields. The API
does not supply a separate verified publisher publication date; `published_at`
stays null. Local date checks use GDELT observations, not verified publication
dates. Publisher names also stay unknown rather than being invented from hosts.
The broad default query deliberately exposes noise. Only GDELT metadata is
fetched; there is no article-body retrieval or silent sample-data fallback.

Before building a weekly ranking, inspect the exports for NBA relevance,
independent reporting, complete query intervals, and usable dates. Publication
date verification, permitted evidence retrieval, and source-list selection
remain necessary. Uncapped API responses alone do not establish completeness.

Reference: [GDELT DOC 2.0 API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/).
It documents date/language/domain filters and the 250-result article-list limit.
A metadata endpoint does not grant rights to publishers' full article text.

For a slow connection, try `--timeout 45 --connect-timeout 30`. Failed attempts
include connection timings in `report.json`. A `tls` failure means TCP connected
but HTTPS negotiation did not complete. Increasing timeouts cannot repair a
server or network outage. Certificate verification stays enabled and user curl
configuration is disabled for predictable behavior.
