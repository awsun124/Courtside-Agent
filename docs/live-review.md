# Live article review

Checked November 10, 2026, using a three-day window, three GNews requests,
and one Yahoo NBA feed request. No LLM requests were made.

The collection returned 30 GNews articles and 50 Yahoo feed headlines.
Both sources responded successfully. Coverage is partial: GNews reached its
request limit and excludes the newest 12 hours, while Yahoo provides a recent
feed snapshot.

## What changed

Some completed games were missed because headlines used "final score",
"loses", or "blot out". Those headlines now qualify when NBA context, two
teams, and an explicit score are present. A score by itself does not qualify.

Reports with the same two teams and score now group despite different wording
or reversed score order. The existing 24-hour limit still applies. Conflicting
scores and different opponents stay separate.

Reprocessing the same collection increased included articles from 15 to 18.
The resulting 15 story candidates include grouped Spurs versus Suns and
Wizards versus Pistons reports. There are still zero eligible ranked stories:
no candidate meets the independent coverage minimum. Yahoo feed links retain
Yahoo attribution and do not become separate publishers just because their
headlines differ.

## What this establishes

Live collection works, and the revised game rules recover real result headlines.
This small sample does not establish broad NBA coverage or clustering accuracy
for every event type. Trade speculation and other ambiguous headlines still
need investigation. The ranking evidence minimum remains two publishers.

Local collection and processing files are in `artifacts/fresh-review/`, which
is ignored by Git. They contain the saved live results used for this review.

## Targeted search follow-up

Later on November 10, a GNews search for `Thunder Wizards` used the same
three-day window and one request. It returned 10 articles from 28 reported
matches. Nine article URLs were additional to the original collection.

Combining those results with the original collection produced one eligible
ranked candidate: Oklahoma City's 114-75 win over Washington. The group had
five publisher labels and three estimated reporting groups. Toronto Star,
WTOP, and Schenectady Gazette were grouped as likely copies of the same
AP report. Tulsa World and Heavy were separate estimated groups. Original
reporting and ownership independence have not been manually verified.

The second planned query, `Lakers Pistons`, received HTTP 429. The third query
was skipped, and no retries were made. That response does not establish whether
the limit was a short request rate limit or an exhausted quota.

This suggests targeted searches can recover relevant coverage that a broad
`NBA` search misses within a small result budget. It does not establish how
well that approach works across many stories. This experiment informed the
bounded corroboration step described below.

Saved query responses and the combined processing results are in
`artifacts/targeted-review/`. The dashboard database was not changed by this
experiment. No LLM requests were made.

## Corroboration during refresh

Live refreshes now reserve one GNews request for targeted corroboration when
the configured budget is at least two requests. The default three-request
budget permits two discovery requests and one targeted request. A one-request
budget continues to run discovery only.

After discovery, deterministic code selects the newest game candidate with
one estimated reporting group and searches its two team nicknames. Candidates
newer than GNews's 12-hour cutoff are skipped. If no candidate qualifies, the
reserved request is unused. Other event types are not targeted yet.

The targeted step shares the existing collection deadline, waits two seconds
after discovery, and makes no retries. A failed discovery prevents the targeted
request. A failed targeted request preserves the discovery results and marks
the source partial. Each recorded API attempt includes its query and purpose.
All results pass through the existing URL deduplication, material restrictions,
story grouping, and ranking rules.

All 136 backend tests passed, including coverage of request limits, publisher
attribution, the 12-hour cutoff, expired deadlines, and targeted failures. The
integrated path was checked with simulated API responses. No further live
requests were made after the HTTP 429 response, so the live impact of this
default budget split remains unverified.

## Integrated live verification

Two local API refreshes on November 10 exercised the new collection path.
Each used three GNews requests and one Yahoo request. Both returned HTTP 200
with explicitly partial coverage. The second saved briefing 8, with no source
errors and one eligible Knicks versus Cavaliers story. Its score was 18.75,
with three publisher labels and three estimated reporting groups. These are
estimates of distinct coverage, not verified publisher independence.

The first refresh exposed duplicate clusters for the same game when one report
omitted the score. Matching teams, a shared named player, and the existing
24-hour window now allow those reports to group. Conflicting known scores
still prevent a match. Player grades, winners-and-losers commentary, watch
guides, and commentary explaining an old quote are now held for review.

All 138 backend tests and 18 frontend tests passed. The frontend production
build passed. The saved live story has three evidence links and a completed
rules investigation. No LLM requests were made. Visual browser verification
remains incomplete because the Chrome automation connection rejected navigation.
Local API responses are saved as `artifacts/live-refresh.json` and
`artifacts/live-refresh-verified.json`.
