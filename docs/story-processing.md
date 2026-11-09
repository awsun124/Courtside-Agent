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

## Story groups

Articles must describe the same event type. Game reports need the same two
teams, compatible scores when supplied, overlapping words, and publication
times within 24 hours. Other supported events need a shared player name,
overlapping words, and publication times within 72 hours. Injury reports with
different body parts stay separate.

The word overlap threshold is 45 percent for game reports and 55 percent for
other events. Overlap is shared distinct words divided by the smaller word set.
These are initial rules, not measured probabilities. Every pair in a group must
pass the check, so a weak match cannot bridge two otherwise separate groups.

Identical normalized headlines or opening excerpts of at least 100 characters
with 90 percent text similarity are treated as likely copies within a story.
The copy count is an estimate. Different wording can hide syndication, and
similar wording does not prove it. The estimated reporting group count never
exceeds the number of publisher labels. Ownership and source attribution still
need a fuller review before numerical ranking.

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
