# Ranking stories

Court Side scores the most-covered stories among its monitored sources. It does
not measure all NBA coverage or decide which events matter most. Numerical
scores come from Python, not an LLM.

```sh
python3 -m courtside.ranking --settings config/ranking.json
```

The command reads `artifacts/stories/stories.json` and writes `ranking.md` and
`ranking.json` under `artifacts/ranking/`. It saves a briefing snapshot and each
candidate's score in SQLite. No network requests or API keys are needed.
Process the articles into the same database first so the briefing can reference
its processing run. Use `--input`, `--output`, and `--database` to change paths.

## Coverage (50 percent)

The script groups articles from the same publisher or source domain. Known
publisher aliases in the settings file can combine related domains. Matching
headlines and near-identical opening text also combine likely syndicated copies.
Copies keep their links but count as one group, even if they appear on several
publisher sites. The group date is its earliest publication date.

The normalized coverage score is:

```text
coverage = min(independent publisher groups / 8, 1)
```

Eight is a fixed, configurable target. A story does not receive full coverage
points just because the other stories in a small sample have little coverage.
Two qualifying groups earn 12.5 of the available 50 coverage points.

These groups are estimates. Publisher ownership and original reporting are not
fully resolved. The copy rules can miss syndication or combine similar reports.

## Momentum (30 percent)

Momentum measures the arrival rate of new publisher groups, not repeated
articles from one publisher. It uses each group's first publication date.
Later copies do not move an old group into the recent period.

The recent period is the last 24 hours of the available coverage window. The
baseline is the earlier part of that same window. Rates are groups per hour,
so periods of different lengths can be compared.

```text
recent_rate = recent groups / recent hours
earlier_rate = earlier groups / earlier hours
growth = max(0, (recent_rate - earlier_rate) / (recent_rate + earlier_rate))
momentum = growth * min(total groups / 3, 1)
```

If both rates are zero, growth is zero. If the earlier rate is zero and recent
coverage exists, growth is one, then the sparse-data adjustment applies. One new
group can earn at most a third of the momentum points. Equal or declining rates
earn zero. This component measures upward momentum rather than penalizing
stories for slowing down.

The default requires at least 24 earlier hours. Shorter baselines receive zero
momentum with a visible explanation. The period lengths and sparse-data threshold
are configurable. On GNews free access, the coverage window ends 12 hours before
collection, so momentum describes that delayed window rather than right now.

This first version measures new publishers joining a story. It does not yet
measure how often one newsroom publishes meaningful updates.

## Freshness (20 percent)

Freshness requires a reviewed development with a time and supporting article
URLs. Publication time alone does not establish a substantive development.
Without reviewed evidence, freshness is zero and the report says why.

Reviewed developments can be attached to a story in the input JSON:

```json
{
  "developments": [
    {
      "occurred_at": "2026-11-08T12:00:00Z",
      "reviewed": true,
      "evidence_urls": ["https://example.com/original-report"]
    }
  ]
}
```

This example is a format illustration, not news data. Each URL must belong to
an included, in-window article from that story. The development cannot be newer
than its evidence or the briefing time. The code validates references and dates.
A person or a later investigation stage must assess the substance of the claim.

The latest reviewed development receives exponential decay with a configurable
24-hour half-life:

```text
freshness = 2 ** (-hours since development / 24)
```

A development 24 hours old gets half the freshness points. The reference time
is the collection time saved with the input, so rerunning the same input produces
the same scores. A later copied article cannot refresh that development.

## Total score and selection

```text
score = 100 * (0.5 * coverage + 0.3 * momentum + 0.2 * freshness)
```

Weights must be finite, nonnegative, and add up to one. Other settings must be
positive. Scores sort from highest to lowest, followed by coverage and story ID
for repeatable ties. An article cannot occupy more than one story's evidence.

The default requires two estimated independent publisher groups to select a
story, and shows at most ten. Scores for excluded candidates remain available
with reasons. The evidence threshold is configurable but should not be lowered
just to fill ten slots.

Incomplete collections, delayed sources, unreviewed groups, missing freshness
evidence, and insufficient baseline time are labeled experimental. Rumor labels
and source links stay attached. An empty selection is a valid result.

## Current saved sample

The 30-article sample produced five story candidates, each with one estimated
independent publisher group after copies were collapsed. All five received a
provisional score, but none meets the default selection minimum. None has a
reviewed substantive development, so freshness is zero. These results demonstrate
the calculation and its limits, not a reliable weekly top ten.

Next, collect a fuller sample, review the groups and developments, and compare
briefings before connecting the scores to the dashboard.
