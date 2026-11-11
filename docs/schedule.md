# Daily collection

The standard FastAPI app collects the past seven days once daily at 6 AM
Eastern. One saved edition serves every visitor. Team and story-type filters
run in the browser over that edition, preserving the overall scores and ranks.
No accounts, additional news calls, or personalized model requests are needed.
Team choices come from teams identified in direct story evidence. These
filters search saved candidates, not every article in the collection.

## Running locally

Start the backend with `.venv/bin/python -m uvicorn courtside.api:app` and
the frontend with `npm run dev` from `frontend/`. Keep provider keys in `.env`.
Scheduling starts with the backend, without another service or scheduler package.
The background task checks the time once per minute. Eastern daylight saving
changes are handled with Python's time zone database.

If the backend starts after 6 AM, it collects today's edition if none has
already been collected after that time. Earlier missed dates are not replayed.
SQLite records a unique daily collection claim before requests start, preventing
workers or restarts sharing the same database from repeating a day's collection.
Keep this database on persistent storage in deployment.

An unsuccessful or interrupted daily attempt keeps its claim until the next
day. This deliberately avoids repeated provider calls after failures. Saved
news remains available and refresh failure or stale notices identify problems.
A partial collection can still save usable stories with source warnings.
The next update time is a scheduled attempt, not a promise of successful news.

Live manual collection is disabled in the public API. Reload briefing reads
SQLite only. Sample mode remains separate and can still generate fictional news.
The optional sample AI demo retains its separate usage limits.

## Hosting limitation

This scheduler runs only while the Python server is awake. A sleeping laptop
or paused free hosting instance cannot collect at 6 AM. On waking, today's
missed collection is attempted. Reliable on-time updates require an always-on
process or an external scheduler in a later deployment step. The app does not
set up hosting or incur hosting charges.

Tests can pass `scheduled=False` to `create_app` to use manual fixtures.
Injected collectors and clocks disable scheduling by default unless explicitly
enabled. Those manual tools retain their 30-minute cooldown.
