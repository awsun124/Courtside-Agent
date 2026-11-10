# Separate saved-sample check

This offline check reused `artifacts/gnews-validation/report.json`. It excluded
all canonical URLs present in the recent 80-article review and 60-article source
review. Sixteen articles remained. No source requests, LLM calls, or changes to
classification rules were made during this check.

## Results

Expected decisions were assigned from the saved headlines and descriptions
before running the processor. All sixteen matched:

| Expected category | Articles | Matching decisions |
| --- | ---: | ---: |
| Betting promotions excluded | 8 | 8 |
| Specific event reports included | 3 | 3 |
| Standings or commentary left for review | 5 | 5 |

The three included articles contained two versions of one injury update and one
game report. They produced two candidates. The matching injury headlines counted
as one estimated reporting group despite having two publisher links. Neither
candidate met the unchanged ranking minimum, so the output contained zero ranked
stories. This is the intended behavior for insufficient independent coverage.

The review did not identify a reason to change the rules. It did not alter source
permissions, rankings, the dashboard's saved briefing, or refresh history. Local
results are in `artifacts/separate-review/`, which stays ignored by Git.

## What this establishes

The recent changes did not break these older examples. This is not a measured
100-percent accuracy result for NBA news. The subset is small, half consists of
betting promotions, and some injury examples were familiar from earlier project
development and regression tests. Removing overlapping URLs does not make the
remaining examples a fully independent or previously unseen evaluation set.

Facts, event dates, and original reporting were not independently verified. The
next stronger check should use a fresh, separately collected sample with more
transactions, injuries, and ambiguous related events. Label it before tuning the
rules against it, and assess grouping as well as individual article decisions.
There is no evidence here that adding an LLM is necessary to fix these cases.
