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
