# News coverage review

Reviewed November 9, 2026. No paid services or LLM calls were used.

## What changed

GNews collection now splits the accessible period into balanced time windows.
Each window gets one page before any window gets a second page. The number of
windows is the smaller of the requested days and request budget. A seven-day
request with only three requests therefore samples three wider windows across
the whole period. It does not claim to cover every day completely.

Windows have nonoverlapping boundaries, separate pagination, reported totals,
and completion flags. Articles must fall within the window that returned them.
Request limits, time limits, the 12-hour delay, URL deduplication, and stopping
on source errors remain in place. Failed or unvisited windows cannot produce a
complete collection or a misleading total.

The same collector powers manual dashboard refreshes. The dashboard still uses
its existing three-request budget. Changing the strategy does not increase it.

## Live three-day check

```sh
python scripts/validate_gnews.py --days 3 --max-requests 6 --output artifacts/source-review
```

The check used six successful requests, two pages per window:

- 60 unique article URLs, no duplicate URLs or rejected records.
- 36 publisher labels, not 36 verified independent newsrooms.
- 267 matches reported across the three windows, so collection remains partial.
- Publication dates: 20 articles on November 7, 24 on November 8, and 16 on November 9 UTC.
- The requested period also included part of November 6. No fetched articles
  came from that portion, which shows the remaining bias toward newer items
  within each window.

The earlier three-request check returned 30 articles from only November 8.
These runs happened at different times and used different budgets. They are not
a controlled comparison. Offline tests separately verify the allocation change.

## Manual metadata review

I reviewed all 60 headlines, publisher labels, filtering decisions, and story
groups. I inspected the available descriptions for suspicious inclusions. This
was not a full-page fact check or proof of independent corroboration.

Three false inclusions prompted rule changes:

- A retrospective about a 1970 playoff game now needs review.
- A roundup of several trade rumors now needs review instead of becoming one event.
- General discussion of offseason workouts and injury problems now needs review
  instead of being treated as a specific injury development.

After those changes, 10 articles were included, 49 needed review, and one betting
promotion was excluded. The included articles formed seven candidates. Only one
candidate met the existing two-reporting-group minimum. Its two sources covered
the same Lakers-Pistons game. That is an estimated grouping, not verified
independence. Several other apparent repeated reports were already discounted
as likely copies. I did not lower the evidence threshold to fill the dashboard.

The offline rules investigator completed for the eligible candidate and produced
attributed source excerpts. It did not verify the underlying claims, mark a new
substantive development, or use a live LLM.

The small fixture in `tests/fixtures/news_review.json` contains adapted examples
of the reviewed failure patterns, rather than copied article bodies. Regression
tests check their expected decisions.

## Publisher feed checks

One direct request to each endpoint returned HTTP 200 and parseable RSS:

| Publisher | Items | Dates present in this response | Assessment |
| --- | ---: | --- | --- |
| ESPN | 13 | November 9, about three hours apart | Useful current headlines, too shallow for a three-day backfill |
| CBS Sports | 36 | November 3 to November 9 | Promising candidate for a separate trial |
| Yahoo Sports | 50 | November 9, about thirteen hours apart | Useful current headlines, shallow history and possible syndicated coverage |

Endpoints checked:

- https://www.espn.com/espn/rss/nba/news
- https://www.cbssports.com/rss/headlines/nba/
- https://sports.yahoo.com/nba/rss/

Browser research initially encountered verification and rate-limit responses.
Direct requests later succeeded. One success does not establish reliability.
Feed availability does not establish permission for redistribution or LLM use.
No feed has been integrated into the production collector yet.

## Recommendation

Keep GNews while measuring relevance and grouping quality. Next, evaluate CBS's
NBA feed against the saved GNews collection for genuinely additional reporting,
not just additional URLs. Confirm publisher terms before integrating it. ESPN
and Yahoo would need ongoing collection to build a multiday window from their
short feed histories.

Keep the three-day focus and clearly label partial coverage. The current single
eligible story is not yet a consistently useful briefing. Improve the remaining
review cases and measure source overlap before adding more integrations. A live
LLM evaluation remains a separate, explicitly approved step.

GNews Free currently provides 100 requests daily, ten articles per request,
a 12-hour delay, and truncated content. It supports noncommercial use. Confirm
the intended public portfolio use and content permissions before deployment.
A paid API plan does not itself grant all publisher content rights.

References:

- [GNews search parameters](https://docs.gnews.io/endpoints/search-endpoint)
- [GNews plans](https://gnews.io/)
- [GNews terms](https://gnews.io/legal/terms-of-service)
- [CBS Sports RSS directory](https://www.cbssports.com/xml/rss)

Detailed JSON, CSV, processing results, and investigation results are saved under
`artifacts/source-review/`. Those local artifacts and the API key stay ignored by Git.
