# NBA statistics

Checked November 11, 2026. No API key, paid service, or new Python package was
needed. We tested the NBA.com endpoints documented by the community nba_api
project directly, rather than adding its full package and data dependencies.

## Live validation

The leagueleaders endpoint returned HTTP 200 with 300 player rows for 2026-27,
Regular Season, PerGame, Scope S. The response included points, rebounds,
assists, steals, blocks, games played, player IDs, and team abbreviations.
The returned season and per-game parameters were checked before caching.

LeagueDashTeamStats timed out twice with a 15-second bound, including one
request with the full documented parameter set. LeagueStandingsV3 also timed
out once. This is evidence of an access or availability problem in this
environment, not proof those endpoints never work elsewhere. Team records
have not been validated live and are visibly unavailable in the dashboard.
The parser and table for successful future standings responses are tested
with clearly synthetic offline fixtures. No fictional data is shown as live.

Raw probe responses and results stay in ignored artifacts/nba-stats-check.
The validated player response was used to populate SQLite without requesting
it again. The cached collection timestamp is the actual validation time.

## How it works

The Stats navigation link opens /stats. GET /api/stats reads SQLite only.
The daily scheduler makes at most two additional source calls, one for
players and one for standings, after its news check. A persistent daily claim
prevents worker or restart duplication. These calls are separate from news
provider requests. Failed sources keep their last successful rows, with an
error and original timestamp. The page marks data older than 26 hours stale.
It never silently substitutes another season or sample statistics.

The page shows five leaderboards together for points, rebounds, assists,
steals, and blocks per game, each with five leaders and an expandable full list.
Eastern and Western team records appear together below when available. Minimum games defaults to five and can be changed.
This is a display filter, not official NBA leaderboard qualification. Equal
values share a rank, and ties at the fifth preview row may be truncated. Team filtering
uses returned abbreviations. Team records, when available, sort by winning
percentage with alphabetical ties, rather than claiming official playoff seeds.
Advanced team efficiency metrics are not implemented.

## Limitations and sources

NBA endpoints are not a contracted developer service. A successful local player
request does not establish reliability on a future hosting provider or grant
permission for every use. Validate access and applicable NBA terms before a
public deployment. The daily task requires the backend to remain awake.

Community endpoint references:

- https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leagueleaders.md
- https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguedashteamstats.md
- https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguestandingsv3.md

Run backend checks with .venv/bin/python -m unittest discover -s tests and
frontend checks with npm --prefix frontend test and npm --prefix frontend run build.

## API-Sports check

The user's server-side API_SPORTS_KEY authenticated successfully against the
API-NBA status endpoint. The account reported an active Free plan with a
100-request daily allowance. A standings request for season=2026 returned
HTTP 200 but a provider error: the free plan permits seasons 2022 through 2024,
not the current season. HTTP success is therefore insufficient validation.
No current team rows were returned, no paid plan was enabled, and historical
standings were not substituted into the current-season dashboard. The key is
not integrated into scheduled collection because this plan cannot satisfy it.
Redacted test results remain in ignored artifacts/nba-stats-check.

## Working current-season team source

A later live test of ESPN's public standings endpoint succeeded for season=2027,
which means the 2026-27 NBA season. It returned 30 unique teams, 15 per conference,
and 160 total wins matched by 160 losses. The response identifies regular season
with seasonType=2. No account, key, or paid plan was needed.

Team collection now uses that endpoint directly instead of the timing-out NBA
standings endpoint. Player collection still uses NBA.com. Each source has its
own name, URL, successful collection timestamp, error status, and stale flag.
The tested ESPN response was cached without requesting it again or changing
the original player collection time.

The team tables include wins, losses, calculated winning percentage, points
scored per game, points allowed per game, and their calculated difference.
The parser rejects a different season, preseason/playoffs, duplicate teams,
missing conferences, partial team coverage, and invalid numeric records. Failed
collections preserve earlier successful rows. No old-season fallback is used.

This is a publicly accessible ESPN site endpoint, not a formally supported
commercial developer API. Local access has been tested, but public-use terms
and availability on the eventual host still require review before deployment.

Tested URL:
https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season=2027&seasontype=2

Community client endpoint reference:
https://sportsdataverse-py.sportsdataverse.org/docs/0.0.73/nba/reference/site
