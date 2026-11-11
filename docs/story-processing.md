# Story processing

The next step after collecting articles is deciding which ones describe an NBA
event and which ones belong together. This version runs on saved results and
does not use an LLM or make network requests.

## Article decisions

The parser checks each URL, publisher, publication date, and collection date.
It checks the requested dates again and drops repeated URLs after removing
tracking parameters. Invalid records are reported without discarding good ones.

The filter checks the headline and opening description before looking at
related names. An injury mentioned in a betting preview does not turn the
preview into injury reporting. Betting previews and promotions are excluded.
Roundups and schedules go to review because one article may describe several
events. Articles without a clear team or supported event also go to review.

All article decisions and reasons are saved, including excluded articles.
Game candidates need a result or performance cue in the headline. A result
mentioned only in an interview or analysis description does not establish direct
game coverage. Live updates, player ratings, and milestone-focused pieces stay
in review. An alternate gallery URL is skipped when the same publisher supplies
an article with the identical headline.

## Story groups

Articles must describe the same event type. Game reports need the same two
teams and compatible scores when supplied, with publication times within
24 hours. When either score is missing, direct game reports must be published
within 18 hours of each other. Other supported events need a shared player name,
overlapping words, and publication times within 72 hours. Injury reports with
different body parts stay separate.

The word overlap threshold is 55 percent for other events.
Overlap is shared distinct words divided by the smaller word set.
These are initial rules, not measured probabilities. Every pair in a group must
pass the check, so a weak match cannot bridge two otherwise separate groups.

Identical normalized headlines or opening excerpts of at least 100 characters
with 90 percent text similarity are treated as likely copies within a story.
The copy count is an estimate. Different wording can hide syndication, and
similar wording does not prove it. The estimated reporting group count never
exceeds the number of publisher labels. Ownership and source attribution still
need a fuller review before numerical ranking.
Explicit shared wire or reporter attribution also counts together during ranking.

Rumor wording in headlines stays labeled. All groups require review. Grouping
does not assign ranks. The separate [ranking step](ranking.md) scores the groups
and labels missing evidence. No generated summaries are presented as verified news.

## SQLite

- `articles` keeps original URLs, publishers, dates, and metadata.
- `processing_runs` keeps each input window, completeness flag, decisions, and results.
- `story_clusters` keeps the story candidates for each run.
- `story_articles` links groups to their articles.
- `briefings` keeps ranking settings, warnings, and each briefing snapshot.
- `story_scores` keeps every candidate's score and evidence breakdown.

Saving another run updates matching article URLs and adds a separate history
entry. Each run keeps its own article snapshot in its saved results. Writes use
one transaction, so a failed save does not leave half a run behind. Ranking adds
briefing history and deterministic scores. Investigation logs come later.

## Current limitations

The 30-article GNews input is a partial sample. Its free plan also excludes the
latest 12 hours. Processing it cannot restore the missing coverage. Player names
come from a simple text rule rather than a complete player directory. Some
player-only headlines, comments, coaching stories, awards, and disputes stay in
review. Repeated games and separate developments can still be hard to distinguish
with short excerpts. We need a larger, manually checked sample before trusting
the groups as input to a most-covered ranking.


The processor now uses verified feed categories as NBA context and recognizes additional event types. See [the saved article review](filter-review.md) for the changes, same-input results, and remaining limitations.

## Related reading

Each story can include up to five related links from collected articles held for review. These are separate from direct evidence, publisher counts, ranking components, and investigator input. Only headlines, publisher names, dates, and original links are shown. Source text restrictions still apply.

Matching currently supports game context mentioning both opponents, or injury context naming the same player and body part, within 36 hours of a direct report. Sharing only a team or player does not qualify. Betting, trade speculation, previews, and likely copies are omitted. Matching is an estimate and can miss useful context. Existing saved briefings need a manual refresh to include this section.
