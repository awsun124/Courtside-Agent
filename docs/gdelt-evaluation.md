# GDELT test results (November 9, 2026)

Command run from this checkout:

```sh
python3 scripts/validate_gdelt.py --days 7 --retries 0 --timeout 20 --max-requests 10 --max-seconds 180
```

Requested UTC window: November 2, 05:59:04 through November 9, 05:59:04.
Seven sequential daily requests were made, at least six seconds apart after
completion. No keys, LLM, paid services, or article-body retrieval were used.

Results:

- Three requests returned GDELT rate-limit messages.
- Four requests failed with curl SSL connection timeouts.
- No article records were retrieved in this run. This does **not** mean no NBA
  articles exist. Relevance, publisher diversity, historical coverage, and live
  cap splitting could not be assessed from this run.
- Exit code 2 correctly marked the result partial/unverified. JSON, CSV headers,
  and a readable report were exported to `artifacts/gdelt-validation/`.

Thirteen offline tests passed, covering timestamp filtering, attribution,
canonical URLs, title groups, relevance hints, rate-limit/schema errors, paced
retries, request/time budgets, capped-window splitting, and safe exports.
The tests use injected responses and a virtual clock, not external services.

Keep the GDELT script for testing, but do not use it as the only source for a
weekly ranking yet. The API rejected requests with rate limits. Connection
timeouts may also involve this network and do not prove GDELT is down everywhere.
Try again later or test another news API before choosing a source for the app.
RSS alone cannot guarantee on-demand seven-day history.

## Connection troubleshooting

A follow-up diagnosis reached the API over TCP but stalled during HTTPS setup.
The GDELT blog connected successfully. Clean IPv4/HTTP 1.1 and TLS 1.2 probes
also stalled with a ten-second connection limit.

The collector now exposes `--connect-timeout`, disables personal curl config,
records connection timings on failures, and applies a 30-second cooldown after
rate limits across both retries and subsequent windows. TLS verification remains
enabled. Sixteen offline tests pass, including transport parsing and cooldowns.

The updated collector was tested with a 35-second connection limit and a
45-second overall request limit, exporting to `artifacts/gdelt-connection-check/`.
HTTPS completed in 9.82 seconds. GDELT then returned HTTP 429 after 12.06 seconds
total. No article data was returned. This shows the timeout is not deterministic,
and GDELT throttling remains a separate limitation. These changes improve
diagnostics and retry behavior but do not establish reliable live collection.
