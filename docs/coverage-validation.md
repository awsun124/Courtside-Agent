# Live coverage validation

Date: November 10, 2026. All displayed times use America/New_York.

## Status

Completed three live refreshes. Review the table and source limitations before drawing conclusions.

This is one bounded local validation job, with up to three live refreshes. It uses the normal three-request GNews budget plus the configured feed, respects the daily guard and refresh cooldown, and makes no LLM requests.

## Saved live baseline

| Briefing | Window | Saved articles | Eligible stories | Estimated groups in ranked stories |
| --- | --- | --- | --- | --- |
| 8 | 3 days | 79 | 1 | 3 |
| 9 | 3 days | 80 | 2 | 4 |
| 10 | 3 days | 77 | 1 | 2 |
| 12 | 3 days | 77 | 1 | 2 |
| 13 | 3 days | 78 | 2 | 7 |

These snapshots used different collection times and code versions. They are a baseline, not a controlled comparison. Briefing 7 is excluded because it contained a known duplicate-game cluster. Briefing 11 used a seven-day window and is not directly comparable.

## Review finding and fix

The latest saved Lakers-Hawks story counted SFGATE separately from Toronto Star and Schenectady Gazette, even though their supplied descriptions carried the same AP report. Choosing the content excerpt before the description hid a matching opening when excerpt lengths differed.

Copy detection now compares both supplied opening fields. The same rule is shared by clustering and ranking. Reprocessing briefing 13 without new source requests combines the three AP copies into one estimated group. That Lakers story drops from five groups to four. The briefing still has two eligible stories, with six total groups instead of seven. All source links are retained. Existing saved briefings are not rewritten.

All 171 backend tests passed, including matching descriptions with unequal excerpt lengths and a guard against merging short generic descriptions.

## New live runs

| Run | Time | Outcome | Requests used | Eligible stories | Estimated ranked groups |
| --- | --- | --- | --- | --- | --- |
| 1 | Nov 10, 07:00:07 PM EST | partial | 2 | 1 | 2 |
| 2 | Nov 10, 07:12:10 PM EST | partial | 2 | 1 | 2 |
| 3 | Nov 10, 07:19:04 PM EST | partial | 2 | 1 | 2 |

All three runs returned the same source pattern. Yahoo supplied 50 feed entries from one publisher label. GNews discovery returned 10 results from 10 publisher labels, but reported that some matches were not downloaded. The combined collection produced one eligible story with two estimated reporting groups.

No targeted searches ran. The collector skipped them because no additional eligible candidate was available outside the recent-search cooldowns. These runs therefore do not measure whether targeted searches can add reporting groups.

## What this shows

The current monitored sources produced only one eligible story in each three-day briefing, far short of ten. This is evidence of sparse usable coverage in these runs, not proof that the sources always return only one story. GNews also reported a partial result, and Yahoo's 50 feed entries represented one publisher label, so the raw article count overstates source breadth.

The next useful improvement is to add another permitted sports news feed or provider and measure its incremental eligible stories and reporting groups. These runs alone cannot tell us which provider will help most. Do not treat Yahoo feed entries or publisher labels as proof of independent reporting.

## Limits

New runs use the same current code, three-day window, and request budget. Repeated runs also inherit cooldown history, so later runs can select different candidates or use fewer requests. Source contents may change between runs. A few refreshes cannot establish consistent improvement across days, and publisher labels do not prove original reporting.

Full responses are stored locally under the ignored `artifacts/coverage-validation-run-*.json` paths. The job status is `artifacts/coverage-validation-status.json`. No credentials are written.
