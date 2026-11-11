# Feed collection

Live refreshes now combine GNews with the reviewed Yahoo Sports NBA RSS feed.
Yahoo needs no key. GNews remains optional and needs its existing server-side
key. Sample mode remains separate and makes no source requests.

## Source configuration

`config/sources.json` selects feeds from the fixed catalog in `courtside/feeds.py`.
Yahoo is enabled. Ten other researched feeds are listed but disabled because
permission for this app's use has not been established. Enabling a pending feed
fails configuration validation rather than silently fetching it. A future usage
review should update its catalog policy before it is enabled. Arbitrary URLs
cannot be supplied through refresh requests or the source settings.

Yahoo's [RSS terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html?ncid=mbr_idnedulnk00000001)
permit display of the provided content without modification, require attribution
and article links, and prohibit advertising within feeds. Our implementation is
limited to feed headlines, dates, publisher labels, and links. It does not copy
images, descriptions, or the full content included in some feed items. XML and
HTML entities are decoded for plain-text display. This is not a general license
for article reuse, advertising, or AI processing. Recheck applicable terms before
public deployment or changing the use.

The terms do not clearly address grouping and ranking headlines. The current
pipeline uses Yahoo headline metadata for those calculations, even though it
withholds feed excerpts from AI investigation. Confirm that use with Yahoo
before public deployment.

Feed material has `investigation_allowed: false`. It is excluded from investigation
and generated summaries. Mixed-source stories use only their permitted evidence
for summaries, while stories without permitted evidence show headlines and links.
Scores still run in deterministic code. Duplicate articles
found through both RSS and GNews inherit the restrictive policy. Headlines and
source links remain visible, with an explicit note when no summary is available. Other eligible
stories can still use the rules investigator. No source permissions are inferred
from a successful HTTP response.

## Collection and storage

Feeds run first with a shared budget of at most 25 seconds. Each request has a
12-second maximum, a two-megabyte response limit, and no retries or redirects.
GNews uses the remainder of the existing 90-second collection budget. Up to four
reviewed feeds are allowed by configuration. The current setup uses one.

The API's `max_requests` still controls GNews requests. Enabled feeds each reserve
one additional request against the existing 30-request daily application guard.
A normal refresh therefore reserves at most four requests: three GNews and one
Yahoo. Actual attempts replace that reservation on success. Unexpected failures
retain a conservative reservation. Standalone evaluation scripts are separate
from this application counter.

The parser accepts RSS channels, validates dated headlines and article hosts,
rejects unsafe XML declarations, and filters dates to the selected window. Feed
bodies are not fetched from article links. HTML is never rendered from feed data.

Canonical URLs merge across collectors. Each saved article retains its original
URL, publisher label, publication date, collection time, material policy, and
collection-source IDs. Duplicate discovery does not create another publisher or
article. Matching URLs alone do not identify every syndicated copy. Publisher
labels do not prove original authorship or independent reporting.

SQLite processing and briefing snapshots retain per-source outcomes, fetched
counts, timestamps, delays, and warnings. The dashboard's Collection sources
panel shows these separately. A missing GNews key can produce a live feed-only
briefing, clearly marked partial. Failure of one source does not discard another
source's successful results. Total failure preserves the last briefing. Failed
feeds never acquire a successful collection timestamp.

## Date coverage

A feed is a recent snapshot, not an archive. This version does not accumulate old
feed items across refreshes into a full historical collection. A seven-day window
can therefore contain much less than seven days of coverage. This stays labeled
partial, even after a successful feed request. The overall available end is the
latest available end among successful sources. GNews's 12-hour delay remains
visible separately and does not apply to Yahoo.

## Live verification

November 9, 2026: the normal service refresh used three GNews requests and one
Yahoo request. It saved 80 unique articles, with 30 GNews articles and 50 feed
articles. No duplicate URLs occurred in this run. Processing included nine
articles, marked 70 for review, and excluded one. Seven candidates formed, one
met the ranking minimum, and four candidates were excluded from investigation
because they contained restricted feed material. The rules investigator ran for
permitted candidates. Zero LLM calls were made.

This verifies the new path works, not that coverage is sufficient. The many review
cases show that filtering and event recognition remain conservative. Adding
feeds alone does not solve those limitations. Full-page facts and publisher
independence were not verified.
