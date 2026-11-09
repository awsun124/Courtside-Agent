# Free NBA source candidates

Research and direct endpoint checks: November 9, 2026. Yahoo has since been enabled for attributed headline display. Other feed candidates remain disabled. See [feed collection](feeds.md).

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

## Recommended pool

Evaluate ESPN, CBS, Yahoo, The Athletic, and New York Post first for news breadth.
Then evaluate Hoops Rumors and RealGM for transactions and leads. Treat their
references to another outlet as attributed coverage, not automatic independent
corroboration. The remaining working feeds can expand discovery after relevance
and overlap checks. These priorities are implementation judgments, not measured
accuracy ratings.

Before enabling each source, record its permitted display, retention, and AI
processing uses. This research did not establish app-specific permission for the
eleven working feeds. Start with permitted metadata and source links, not copied
full articles or publisher images. RSS access and full article access are separate.

Keep one shared article schema, canonical URL deduplication, original reporting
attribution, and per-source success dates. Fetching the same article through
GNews and a direct feed must not add another publisher or reporting group.

## Other free API options

| Service | Documented free offering | Fit for Court Side |
| --- | --- | --- |
| [Guardian Open Platform](https://open-platform.theguardian.com/access/) | Developer key, noncommercial use, 500 calls daily, one per second | Potential supplementary original source. Review retention and AI conditions separately. |
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
