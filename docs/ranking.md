# Ranking

Scores describe coverage among monitored sources, not all NBA news. Python
calculates them using config/ranking.json.

Coverage contributes 50%:

```text
coverage = min(reporting groups / 8, 1)
```

Articles sharing a publisher, matching headlines, near-identical excerpts, or
explicit shared attribution count together. Eight groups is the configurable
full-coverage target. These are estimates of independent reporting.

Momentum contributes 30%. It compares new reporting groups per hour in the
latest 24 hours with the earlier part of the available window:

```text
growth = max(0, (recent_rate - earlier_rate) / (recent_rate + earlier_rate))
momentum = growth * min(total groups / 3, 1)
```

If both rates are zero, growth is zero. A zero earlier rate with recent coverage
gives growth of one, reduced by the sparse-data factor. A baseline shorter than
24 hours receives no momentum points. Copies retain the first report's date.

Freshness contributes 20%:

```text
freshness = 2 ** (-hours since reviewed development / 24)
```

The development needs a timestamp and in-story evidence URLs. A newer article
alone does not qualify. Without a reviewed development, freshness is zero.

```text
score = 100 * (0.5 * coverage + 0.3 * momentum + 0.2 * freshness)
```

A ranked story needs at least two reporting groups. At most ten are selected.
Ties sort by coverage, then story ID. Other candidates retain their provisional
scores. Related reading never contributes points. Missing or limited coverage
stays visible rather than being filled with sample news.
