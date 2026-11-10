# Reviewing article selection

This review reused the 80 articles saved in live briefing 5 on November 9, 2026.
It made no new API, feed, or LLM calls. The comparison is saved locally under
`artifacts/filter-review/`. It does not replace the saved dashboard briefing or
pretend that old news was collected again.

## Changes

The processor now records NBA context separately from its event decision. A
recognized NBA feed ID must match its catalog endpoint before its category can
supply context. An NBA-specific feed can therefore identify an ambiguous team
nickname without requiring the headline to repeat NBA. A category still does
not establish that the headline describes one current event.

The supported events now include narrowly recognized All-Star host announcements,
player record milestones, and reports about an arrest involving stalking or
home trespass. These are discovery categories, not factual verification. Host
announcements need a city and event year. Off-court reports need one recognizable
person and an incident type. Milestone grouping requires matching numeric
anchors. Unknown or ambiguous events still need review.

Game recognition accepts phrasing such as a player leading one team past another.
Headline event wording takes priority over incidental injury mentions in the
opening description. Games still need two teams, compatible scores, and a close
publication window.

Fantasy advice, pregame availability lists, evaluations of contracts or teams,
reaction pieces, question headlines, and opinion recaps stay outside automatic
story selection. They remain saved for review, rather than being deleted or
labeled unrelated to basketball. Betting promotions remain excluded.

Grouping checks the event type as well as its participants. Host announcements
need the same city and year. Off-court reports use a matching person, incident,
location category, and a 72-hour publication window. Different players, different
location categories, roster moves, and different numeric milestones stay separate.
The existing game and injury grouping tests remain in place.

## Same-input comparison

I reviewed the metadata and decisions for all 80 articles, including the 70
previously marked for review. Eleven missed reports were admitted and three
weak inclusions were moved back to review. The local review file records an
expected decision for each saved article. This was not a full-page fact check.

| Measure | Before | After |
| --- | ---: | ---: |
| Included articles | 9 | 17 |
| Articles needing review | 70 | 62 |
| Excluded promotions | 1 | 1 |
| Distinct candidates | 7 | 7 |
| Candidates meeting ranking minimum | 1 | 2 |

The newly admitted reports included a host announcement, a title-only game result,
a record milestone, and repeated coverage of an alleged stalking incident.
Eight reports about that incident now form one candidate instead of filling
several story slots. Likely copies still count once within estimated reporting
groups. Source independence has not been verified.

The two qualifying candidates concern distinct events. Neither received a
new generated summary because both contain restricted feed material. Their
scores remain deterministic. The ranking weights, publisher minimum, freshness
requirements, and source permissions were not loosened to improve these counts.

## Remaining limitations

Of the 62 review cases, 31 still lack a specific event recognized by the rules.
The other 31 have explicit format, commentary, historical, or ambiguity reasons.
Some of these can still be useful NBA journalism. Review does not mean irrelevant.

These changes were developed against this small sample. The adapted examples in
`tests/fixtures/event_review.json` cover positive and negative cases, including
misleading NBA mentions, opinion, different event years, players, locations,
statistics, and publication windows. They are regression checks, not an
independent benchmark of classification accuracy.

Names and incident details are extracted with simple rules. Multiple incidents
in the same location over a short period may still merge. A missing detail may
keep related reports apart. Publication dates are not verified event dates.
Additional sources do not automatically establish independent reporting.

The next quality check should use a separate saved sample before expanding the
recognized event patterns further. Existing briefing snapshots stay reproducible.
New rules apply on the next refresh or an explicit offline reprocessing run.


A [separate saved-sample check](separate-review.md) now records results on sixteen nonoverlapping article URLs, with explicit limits on how independent that check is.
