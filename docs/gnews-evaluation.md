# GNews evaluation

Live test on November 9, 2026:

```sh
python3 scripts/validate_gnews.py --days 3 --max-requests 3
```

All three authenticated requests succeeded. The collector retrieved and parsed
30 unique article URLs with 16 publisher labels, provider-supplied publication
dates, and available excerpts. No records were rejected. The API reported 376
matching articles. The 30 fetched records were all dated November 8 UTC because
the request sorts newest first and the small budget stopped after three pages.
This does not evaluate the full three-day distribution or publisher coverage.

The requested window was November 6 at 06:20:42 UTC through November 9 at
06:20:42 UTC. The free plan's accessible end was November 8 at 18:20:42 UTC.
The latest 12 hours were explicitly excluded and labeled, not silently omitted.

The report correctly exited with code 2 for incomplete pagination. A partial
evaluation can still demonstrate successful transport and article parsing.
It cannot establish a most-covered ranking.

Manual metadata inspection found NBA injury reporting and game coverage, but
also betting previews, standings, commentary, and incidental mentions. One exact
normalized headline group appeared on multiple publisher URLs. The title-only
triage is intentionally provisional and missed some betting previews. Publisher
labels are not evidence of independent reporting. No source article bodies were
fetched and no claims were independently corroborated.

The key was sent in an authentication header, not a URL or process argument.
It was verified absent from the generated JSON, Markdown, and CSV exports.
The local `.env` and generated artifacts are ignored by Git. No LLM calls or
paid subscriptions were used. Twenty-five offline tests passed.

Recommendation: proceed with GNews as the next experimental discovery adapter.
Before ranking, assess a fuller seven-day sample within the account's quota,
filter promotions and incidental mentions, identify syndicated reporting, and
verify access to sufficient permitted evidence. Keep the free-plan delay visible.
Public deployment and AI processing permissions remain separate decisions.

References:

- [GNews search](https://docs.gnews.io/endpoints/search-endpoint)
- [Authentication](https://docs.gnews.io/authentication)
- [Article availability](https://docs.gnews.io/article-availability)
- [Terms](https://gnews.io/legal/terms-of-service)
