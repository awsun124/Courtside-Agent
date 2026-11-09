# Court Side API

The API connects the existing collection, grouping, ranking, and SQLite code.
It runs locally with FastAPI and one Uvicorn worker. No background queue or
scheduler is needed for this version.

## Routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Check that the API can read its database |
| GET | `/api/briefings/latest` | Read the latest live briefing and refresh status |
| GET | `/api/briefings` | Read briefing history, newest first |
| GET | `/api/stories/{story_id}` | Read a candidate's score and source articles |
| POST | `/api/refresh` | Collect, process, score, and save a briefing |

Read routes accept `mode=live` or `mode=sample`, defaulting to live. History has
a `limit` from 1 to 50. Story details accept a `briefing_id` to read the exact
article snapshot from an earlier briefing, rather than today's article records.
Candidates below the ranking evidence minimum can still be inspected.

An empty database returns HTTP 200 with `briefing: null` and
`empty_reason: no_saved_briefing`. A saved briefing without eligible stories has
`empty_reason: no_eligible_stories`. Source failure and insufficient evidence
are different states.

## Manual refresh

```json
{"mode":"live","days":3,"max_requests":3}
```

Days can be 1 through 7. The request limit can be 1 through 5, with a default of
3. Collection has a 90-second overall limit and 30 seconds per source request.
Requests are synchronous, so clients should keep their loading state until the
response arrives. The investigation has a separate default 15-second limit after
collection. Saved briefings remain readable throughout the refresh.

The server reads the key from its environment or local `.env` file. Clients do
not submit a key. Unknown request fields are rejected. Collector errors and
unexpected exceptions are returned without private key values or tracebacks.

Successful partial collection returns HTTP 200 with a `partial` refresh status,
the actual number of requests, and experimental score warnings. A source failure
without article data returns HTTP 502 and preserves the previous briefing. A
missing key returns HTTP 503. Database errors also return a safe HTTP 503 response.
Invalid request parameters return HTTP 422.

## Sample mode

```json
{"mode":"sample","days":3}
```

Sample mode creates four fictional articles about two fictional games. Every
headline starts with `Sample`, publisher names start with `Sample newsroom`,
and links use example domains. Dates are relative to the selected window.
No external services, keys, or LLM are involved. The same grouping and ranking
code runs on these records.

Every sample briefing is labeled fictional and experimental. Sample and live
histories are queried separately, so trying a sample cannot replace the latest
live briefing. The server rejects any accidental mode switch from a collector.

## Limits and persistence

SQLite records each refresh attempt before collection starts. It prevents
overlapping refreshes, including requests handled by separate app instances.
An active refresh returns HTTP 409. Live requests also have a 60-second cooldown
between starts and an app-specific allowance of 30 source requests per UTC day.
Limit responses use HTTP 429 with `Retry-After`.

The requested allowance is reserved before collection and replaced by the
actual attempt count when collection finishes. An interrupted process keeps its
reservation, which avoids silently losing request counts. Expired refresh leases
are marked failed when another refresh starts. This is a small local refresh
guard, not a distributed job system.

`refresh_attempts` stores status, request count, timestamps, and the saved
briefing ID. Existing processing runs and briefing snapshots remain intact.
The latest-briefing response uses the snapshot's collection time as
`last_successful_refresh`, and marks it stale after six hours. This is separate
from GNews's 12-hour publication delay. The most recent failed attempt is shown
even when an older briefing remains available.

## Current scope

The API defaults to `artifacts/courtside.db`. It has no startup collection and
no automatic refresh. CORS permits the local frontend at port 5173. Run it on
localhost for development. Public hosting and authentication are later work.

The bounded investigator adds cited source excerpts, uncertainty, activity, and
previous-briefing comparisons. Its default provider is rules, not an LLM. An
unavailable investigation does not remove the deterministic scores. Freshness remains zero
without a reviewed development. The small live sample can still produce zero
eligible stories, and the API keeps that result honest. The dashboard should
show the warnings and candidate evidence rather than inventing ten stories.
