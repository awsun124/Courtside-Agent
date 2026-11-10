# Free NBA source candidates

Endpoint checks: November 9, 2026. Usage terms reviewed November 10, 2026. Yahoo is enabled for attributed headline display. Other feed candidates remain disabled. See [feed collection](feeds.md).

## Direct feed checks

One bounded request was made per endpoint. Eleven of twelve returned HTTP 200
with RSS items and parseable publication dates. These are snapshot results, not
an uptime guarantee or permission to redistribute content. All successful feeds
were accessible without a key.

| Source | Items | Oldest date in response | Newest date | Assessment |
| --- | ---: | --- | --- | --- |
| [ESPN](https://www.espn.com/espn/rss/nba/news) | 13 | 2026-11-08 | 2026-11-09 | Priority candidate. NBA feed with a short current history. |
| [CBS Sports](https://www.cbssports.com/rss/headlines/nba/) | 36 | 2026-11-03 | 2026-11-09 | Priority candidate. Several days present in this snapshot. |
| [Yahoo Sports](https://sports.yahoo.com/nba/rss/) | 50 | 2026-11-09 | 2026-11-09 | Priority candidate. Separate original and syndicated reporting. |
| [Hoops Rumors](https://www.hoopsrumors.com/feed) | 15 | 2026-11-08 | 2026-11-09 | Secondary candidate. Trace claims to original reporting and label rumors. |
| [RealGM](https://basketball.realgm.com/rss/wiretap/0/0.xml) | 31 | 2026-11-06 | 2026-11-09 | Secondary candidate. Useful wire coverage, often cites other outlets. |
| [The Athletic](https://www.nytimes.com/athletic/rss/nba/) | 100 | 2026-10-27 | 2026-11-09 | Priority candidate for permitted metadata and links. Do not bypass article access restrictions. |
| [NBC Sports](https://www.nbcsports.com/nba/rss) | 0 | Unavailable | Unavailable | The tested URL failed. This does not prove no supported feed exists. |
| [The Guardian](https://www.theguardian.com/sport/nba/rss) | 20 | 2026-10-10 | 2026-11-07 | Supplementary candidate. Lower frequency in this snapshot. Prefer documented API after checking applicable terms. |
| [New York Post](https://nypost.com/nba/feed/) | 20 | 2026-11-07 | 2026-11-09 | Priority candidate. Distinguish news from opinion and commentary. |
| [Hoops Wire](https://hoopswire.com/feed/) | 10 | 2026-11-09 | 2026-11-09 | Secondary candidate. Very short history in this snapshot, trace attribution. |
| [Basketball Insiders](https://www.basketballinsiders.com/feed/) | 25 | 2026-10-25 | 2026-11-09 | Secondary candidate. Check basketball relevance and betting promotions. |
| [Bleacher Report](https://feeds.bleacherreport.com/articles) | 615 | 2026-11-02 | 2026-11-09 | Secondary candidate. Large all-sport feed, needs NBA filtering. |

Dates above use each feed timestamp as supplied. Short feeds cannot backfill an
arbitrary three-day or seven-day period. A retained rolling collection would be
needed to accumulate that history. Publication dates alone do not establish the
date of the event.

## Coverage sources to investigate

The feeds above show potential coverage, not permission to collect them. Yahoo
is the only feed currently enabled, and its ranking use still needs clarification.
Treat references to another outlet as attributed coverage, not automatic
independent corroboration. These are coverage observations, not measured
accuracy ratings.

Before enabling each source, record its permitted display, retention, and AI
processing uses. This research did not establish app-specific permission for the
eleven working feeds. Start with permitted metadata and source links, not copied
full articles or publisher images. RSS access and full article access are separate.

Keep one shared article schema, canonical URL deduplication, original reporting
attribution, and per-source success dates. Fetching the same article through
GNews and a direct feed must not add another publisher or reporting group.

## Usage review

An endpoint returning headlines is not permission to store or rank them. These
official terms do not support adding several feeds to the current automated
collection without written permission:

- [ESPN points users to Disney's Terms of Use](https://support.espn.com/hc/en-us/articles/360035445091-Terms-of-Use). Disney's terms restrict automated access to its products without express written permission. The ESPN RSS endpoint worked in the saved check, but I found no RSS-specific license that resolves this restriction.
- [CBS Sports lists an NBA RSS feed](https://www.cbssports.com/xml/rss), but its [Terms of Use](https://www.cbssports.com/info/about/tos/dm) prohibit copying or storing site materials without prior written permission. Do not collect the feed into the app database based only on public availability.
- The [Guardian Open Platform](https://open-platform.theguardian.com/access/) offers a free developer key for non-commercial use, but its [terms](https://www.theguardian.com/open-platform/terms-and-conditions) require deletion or replacement of content within 24 hours and prohibit automated collection, data aggregation, analysis, and AI use. Those terms conflict with this app's pipeline.
- GNews's [current terms](https://gnews.io/legal/terms-of-service) limit free-plan API and data use to personal, academic, evaluation, and other non-commercial purposes. They do not grant rights in the underlying publishers' work. Check with GNews and the relevant publishers before a public portfolio deployment.
- Yahoo's [RSS terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html?ncid=mbr_idnedulnk00000001) allow feed content to be displayed without modification, with attribution and a link, and prohibit adding advertising to the feed. They do not clearly address using headlines to group and score stories. The current collector keeps Yahoo excerpts out of AI investigation, but deterministic ranking still uses headline metadata. Clarify that use with Yahoo before public deployment.

For now, keep the source list unchanged for local evaluation and do not enable
ESPN, CBS, or Guardian. This research did not find another source whose
published terms clearly cover this app's collection, ranking, and optional AI
workflow. Feed availability is not evidence of permission.

## What the saved run says

The latest saved live briefing in the local database is from November 9, 2026.
It collected 30 GNews results and 50 Yahoo feed headlines. Processing formed
seven event candidates, but only one met the ranking threshold. An offline
review of the same 80 articles found event recognition and publisher
independence still leave many articles undecided. This is a small saved sample,
not a current source-coverage benchmark. Adding feeds alone would not fix those
issues.

## Other free API options

| Service | Documented free offering | Fit for Court Side |
| --- | --- | --- |
| [Guardian Open Platform](https://open-platform.theguardian.com/access/) | Developer key, noncommercial use, 500 calls daily, one per second | Not a fit for this pipeline. Its terms prohibit automated aggregation, analysis, and AI use. |
| [TheNewsAPI.com](https://www.thenewsapi.com/pricing) | 100 requests daily, three articles per request | Possible comparison trial, but small pages and untested NBA relevance. Public-use terms still need checking. |
| [NewsData.io](https://newsdata.io/pricing) | 200 credits daily, up to ten articles per credit, 12-hour delay, past 48 hours | Poor immediate replacement for a three-day or seven-day backfill. Not authenticated or tested here. |
| [NewsAPI.org](https://newsapi.org/pricing) | Development only, 100 requests daily, 24-hour delay | Exclude from the free deployed configuration. Its free tier forbids production use. |
| GNews | Already integrated | Keep as an existing discovery source, with the current delay and incomplete-coverage labels. |
| GDELT | Earlier repository tests encountered timeouts and rate limits | Do not make it a required dependency. No fresh test in this research. |

API limits were read from provider pages. No accounts were created and no trials
or paid plans were started. Aggregators can overlap heavily and do not inherently
increase independent coverage.

## Recommended next implementation

Build a small configurable feed adapter and source registry, with independent
timeouts and source status. Enable a manageable initial pool only after each
source passes permission and data checks. Keep other candidates disabled until
validated. This supports broad coverage without requiring a different collector
for every publisher.

Do not claim eleven new independent sources based on eleven working endpoints.
Test returned links, NBA relevance, dates, original attribution, and duplicate
stories first. A single direct request does not measure reliability or unique
event coverage. Raw endpoint results are local in
`artifacts/source-review/feed-checks.json`.

Publisher references:

- [CBS feed directory](https://www.cbssports.com/xml/rss)
- [Hoops Rumors explains player RSS feeds](https://www.hoopsrumors.com/2016/10/following-specific-players-on-hoops-rumors-21.html)
- [RealGM website lists its basketball RSS feed](https://basketball.realgm.com/?full_site=true)
- [Guardian API access](https://open-platform.theguardian.com/access/)
- [Guardian API terms](https://www.theguardian.com/open-platform/terms-and-conditions)
- [NewsAPI free-tier restrictions](https://newsapi.org/terms)

## Additional source research

Checked November 10, 2026. These options were not added to the collector.

| Option | What it adds | Finding |
| --- | --- | --- |
| [BBC Sport RSS](https://www.bbc.co.uk/sport/articles/cqllxj2n4kyo) | A large sports publisher and potentially international NBA coverage | BBC documents RSS for website display with attribution. Its terms say business use needs permission and may cost a fee, and metadata use requires a license. The feed list does not establish a current NBA-specific feed or sufficient NBA volume. Not a clear free fit for this app. |
| [TheNewsAPI](https://www.thenewsapi.com/pricing) | An aggregator that may return publisher domains beyond the existing collectors | Free plan says 100 requests daily and 3 articles per request. It returns snippets and links, not full articles. The API documentation supports date, source, and search filters, but the terms only grant personal, non-commercial use and prohibit automated access to the site. Confirm API-specific rights and test NBA coverage before integrating. |
| [NewsData.io](https://newsdata.io/pricing) | Another multi-publisher aggregator | Free plan advertises 200 credits daily, up to 10 articles per credit, a 12-hour delay, and only the past 48 hours. Its terms say it does not grant rights to third-party raw content. Do not treat the free API key as permission to reuse returned article text. |
| [SportsDataIO NBA news](https://sportsdata.io/developers/api-documentation/nba) | Sports-specific news endpoints | The free trial is limited to UEFA Champions League data, not NBA. NBA news access is therefore not a practical free addition. |
| [NBA.com RSS](https://www.nba.com/rss/nba_rss.xml) | Official league updates | The commonly cited league RSS endpoint returned 404 in this check. A historic team RSS information page still exists, but it did not provide a working league-wide feed. |

The two news APIs could widen the list of publisher domains, but they are
aggregators, not independent publishers. They may return stories already found
through GNews or Yahoo, and their free plans do not settle the underlying
publisher reuse rights. The BBC route is a direct publisher feed, but the
published business-use terms do not establish free permission for Court Side.

**Recommendation:** do not add another automated source yet. If you want to
increase coverage without paying, first request written permission from one or
two direct publishers for headline metadata, links, storage duration, ranking,
and optional AI processing. A second route is to test TheNewsAPI with a free
account for coverage only after confirming that its API-specific terms allow
this personal portfolio project and its limited snippet use. Do not add a
provider response until that permission and the actual NBA results are checked.
