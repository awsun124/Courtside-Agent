# FreeNewsApi.ai

FreeNewsApi.ai now supplements GNews and the enabled RSS feeds. It collects attributed headlines and original URLs through the documented API. Article descriptions and bodies are discarded, and this source's material is excluded from the AI investigator.

## Setup

Add `FREE_NEWS_API_KEY` to the server's ignored `.env` file. Leave it empty to disable this collector. Visitors do not need a key.

`config/free-news.json` controls the publisher hosts and limits. The defaults allow two discovery requests and one targeted request per live refresh. Discovery splits the 22 configured hosts between separate searches so one busy outlet cannot occupy both result pages. Each request returns at most 100 records and retains at most 20 articles per publisher. The targeted search uses all configured hosts to seek more reporting about one game or injury candidate. Some configured publishers may have no matching articles.

Searches that add no reporting groups wait six hours before repeating that query on the same provider. Searches that add reporting groups wait one hour. GNews and FreeNewsApi.ai keep separate search histories. All calls count toward the app's existing daily source-request limit. Failed requests are not retried.

Run the discovery check without refreshing the app or calling an LLM:

```sh
.venv/bin/python -m courtside.free_news --days 7
```

It saves normalized metadata under the ignored `artifacts/free-news-check/` folder. The normal dashboard refresh also performs the optional targeted search and saves collection activity with the briefing.

## Live check on November 11, 2026

The final integration check used three live FreeNewsApi.ai requests. GNews and Yahoo records were replayed from the saved November 10 briefing, so this comparison is not a simultaneous benchmark of the providers.

| Measure | Saved sources | With FreeNewsApi.ai |
| --- | ---: | ---: |
| Article URLs | 60 | 222 |
| Publisher labels | 11 | 22 |
| Eligible distinct stories | 1 | 3 |

The API retained 162 headlines from 12 publishers. Twenty-one passed the event rules, while 141 needed review. The three eligible combined stories covered Warriors vs. Pelicans, Lakers vs. Hawks, and Rockets vs. Nuggets. They had four, three, and two estimated reporting groups respectively. These estimates do not establish independent authorship.

The check exercised collection, processing, ranking, investigation filtering, and SQLite saving in an isolated database. The three live calls plus two replayed source calls were accounted for. No LLM requests were made, and the app's main database was unchanged. Results are saved locally in `integration.json` and `pipeline-check.json` in the artifacts folder.

All 188 backend tests and 28 frontend tests passed. The frontend production build also passed.

## Changes prompted by the results

- Use exact UTC timestamps ending in `Z`. The initial `+00:00` format was rejected, and the shorthand seven-day query returned some future timestamps.
- Validate dates again locally. Reject known crawl-time fallbacks. Missing date provenance remains explicitly unverified.
- Keep publisher names tied to configured URL hosts. Normalize URLs separately for deduplication.
- Exclude betting, proposals, reactions, jersey swaps, and commentary from direct event coverage.
- Recognize name suffixes and uncertain injury absences without turning title words into extra people.
- Group direct reports about the same opponents within 18 hours when a score is missing. Supplied conflicting scores still keep games separate. This avoids splitting one game into several ranked stories because headlines focus on different players.
- Count exact headline copies and explicit shared wire or reporter attribution together. Undetected syndication remains possible.
- Investigate only permitted articles in mixed-source stories. Headlines from this API contribute coverage and links, while summaries cite only permitted retrieved evidence. A story with no permitted material has no generated summary.

## Limits

The provider omitted its documented `date_source` field throughout the inspected samples, including the final retained headlines. Publication times remain provider claims rather than verified dates. Bounded pages can cover only part of the requested seven-day window, and current results are concentrated in a few publishers. The dashboard keeps partial-coverage warnings and shows fewer than ten stories when evidence is insufficient.

The [provider's terms](https://freenewsapi.ai/legal/terms) allow storing and processing API data, but do not license publisher article text. This integration retains metadata and links, not article excerpts. See the [search documentation](https://freenewsapi.ai/docs/search) and [date fields](https://freenewsapi.ai/docs/fields). No underlying publisher rights are inferred from an API response.
