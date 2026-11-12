# Deployment

The frontend is prepared for Vercel. The backend still needs a host with a
persistent disk and a running Python process for daily collection.

Vercel Functions do not provide durable local SQLite storage. The current
background scheduler also cannot be treated as an always-on serverless task.
Do not connect the entire repository and expect those parts to work unchanged.

# Backend

Set these in the host's process environment, using its actual mounted path:

```env
COURTSIDE_DATABASE=/data/courtside.db
COURTSIDE_ALLOWED_ORIGINS=https://your-site.vercel.app
COURTSIDE_PUBLIC_READ_ONLY=true
ENABLE_LLM_CALLS=false
ENABLE_SAMPLE_AI=false
```

These deployment settings are read from the process environment, not .env.
Provider keys belong only in backend secrets. Start from the repository root:

```sh
.venv/bin/python -m uvicorn courtside.api:app --host 0.0.0.0 --port 8000
```

Use the host's port if different. Keep database backups and process restarts
configured. Public read-only mode blocks visitor-triggered writes, including
sample generation and AI calls. Internal daily collection still runs. Save a
sample briefing before enabling read-only mode if you want a sample demo.

# Vercel frontend

- Root Directory: frontend
- Framework: Vite
- Build Command: npm run build
- Output Directory: dist
- VITE_API_BASE_URL: the backend HTTPS origin, without /api

The frontend URL is public configuration. Never put API keys in VITE_ variables.
Redeploy after changing the API URL. vercel.json handles /stats and /ranking.
Local development uses Vite's proxy when the API URL is unset.

# Before launch

Choose the backend host, confirm provider permissions for a public demo, and
test provider access from that host. Public NBA.com and ESPN endpoint access is
not a supported developer-service contract. GNews free access is non-commercial;
review its terms and publisher restrictions before publishing.

After deployment, check direct page links, CORS, shared stories, daily updates,
and database survival after restart. Restore a backup once. Local tests cover
these code paths, but a real cloud deployment has not been verified.

References: [Vercel filesystem](https://vercel.com/docs/functions/runtimes),
[Vite hosting](https://vercel.com/docs/frameworks/frontend/vite),
[GNews terms](https://gnews.io/legal/terms-of-service).
