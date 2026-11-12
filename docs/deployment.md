# Deployment

Use Render Free for FastAPI, Neon for PostgreSQL, and Vercel for the frontend.
SQLite still works locally when DATABASE_URL is unset. Existing SQLite history
stays local. The first collection creates the hosted edition.

## Database

Neon's pooled DATABASE_URL is for the app and collection job. The direct
DATABASE_URL_UNPOOLED is only needed for schema setup. Keep both private.

Run once before starting the backend, with the direct URL in the environment:

```sh
python -m scripts.migrate_database
```

Or use your ignored local file:

```sh
python -m scripts.migrate_database --env-file .env
```

The versioned schema is additive and safe to run again. Future schema changes
need explicit migrations. Startup and ordinary requests do not change the
PostgreSQL schema. Integration tests use disposable schemas on a test branch:
set COURTSIDE_TEST_DATABASE_URL to its direct URL, then run test discovery.

## Render

- Language: Python 3
- Branch: main
- Root Directory: leave blank
- Build Command: pip install -r requirements.txt
- Start Command: uvicorn courtside.api:app --host 0.0.0.0 --port $PORT
- Instance Type: Free
- Health Check Path: /health

Set these environment variables in Render:

```env
DATABASE_URL=your-pooled-Neon-connection-string
COURTSIDE_ALLOWED_ORIGINS=https://your-site.vercel.app
COURTSIDE_PUBLIC_READ_ONLY=true
COURTSIDE_EXTERNAL_SCHEDULE=true
ENABLE_LLM_CALLS=false
ENABLE_SAMPLE_AI=false
```

Render serves saved results. It needs no news-provider or LLM keys. Free services
sleep when idle, so the first request can take longer. The database survives
restarts because it lives in Neon. The /health route checks database access.

## Daily collection

In GitHub Settings > Secrets and variables > Actions, add repository secrets:
DATABASE_URL (pooled), GNEWS_API_KEY, and FREE_NEWS_API_KEY.

The Daily collection workflow runs at 6 AM Eastern and can also be started from
the Actions tab. GitHub may delay scheduled runs and disables public-repository
schedules after 60 days without activity. Check the workflow occasionally.
Daily database claims prevent duplicate collection, including manual reruns.
Failed attempts retain previous results and do not retry providers that day.
LLM calls are disabled. No credentials are stored in the workflow file.

## Vercel

- Root Directory: frontend
- Framework: Vite
- Build Command: npm run build
- Output Directory: dist
- VITE_API_BASE_URL: Render's HTTPS origin, without /api

Set Render's allowed origin to the final Vercel URL. Redeploy the frontend after
changing its API URL. Never put secrets in VITE_ variables.

Before sharing, verify /health, source access from GitHub Actions, the first
edition, CORS, direct /stats and /ranking links, and results after a Render
restart. Provider permissions still apply. GNews free access is non-commercial.
NBA.com and ESPN public endpoints have no supported developer-service contract.

References: [Render Free](https://render.com/docs/free),
[Neon connections](https://neon.com/docs/connect/connection-pooling),
[GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
