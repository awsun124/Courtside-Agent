# Architecture

FastAPI collects articles, groups events, calculates scores, and saves briefings
in SQLite locally or PostgreSQL when DATABASE_URL is set. React reads those snapshots. Opening pages and filtering stories do
not call news or stats providers.

- courtside/sources.py combines GNews, enabled RSS feeds, and FreeNewsApi.ai.
- courtside/stories.py filters articles and groups reports about the same event.
- courtside/ranking.py calculates scores. The LLM cannot change them.
- courtside/investigation.py runs the bounded evidence-checking loop.
- courtside/storage.py and schema.sql store articles, groups, briefings, and logs.
- courtside/schedule.py runs the shared daily collection.
- courtside/stats.py caches NBA.com player stats and ESPN team records.

The investigator can search saved articles, retrieve allowed excerpts, inspect
related groups, and compare previous briefings. Limits live in
config/investigation.json. Tool calls, citations, and short decisions are saved.
Article text is untrusted input. Headline-only sources are excluded from model
input. Summaries must quote retrieved evidence.

# Data limits

GDELT validation returned rate limits and timeouts, so the app uses other
sources. The initial GNews test returned 30 articles from 16 publisher labels,
but covered only a small part of the requested window. Free GNews access is
12 hours delayed. RSS is a recent snapshot, not a seven-day archive.
FreeNewsApi.ai contributes attributed headlines without storing article bodies.

Publisher groups and event matches are estimates. Syndication, ambiguous names,
and short excerpts can cause mistakes. Related reading adds context without
contributing to scores or corroboration. Rumors stay labeled. Freshness remains
zero until a substantive development has reviewed evidence.

NBA.com returned 300 current-season player rows. ESPN returned 30 teams split
between conferences. Stats are per game, regular season, and cached daily.
Minimum games is a display rule, not official NBA qualification. Team ties are
alphabetical rather than official playoff seeding. Failed sources keep old data
with their original timestamp and a visible warning.

Team filters, keyword search, bookmarks, unread markers, and spoiler preferences
run in the browser. Bookmarks keep up to 50 saved stories. Read status keeps up
to 2,000 story IDs. These preferences do not sync between devices. New event IDs
can make an old story appear unread again.
