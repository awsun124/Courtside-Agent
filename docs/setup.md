# Setup

Requires Python 3.11+, Node.js 22, and curl.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
npm --prefix frontend ci
```

Add your news keys to .env. Sample mode works without keys. Stats use public
NBA.com and ESPN endpoints without a key. API_SPORTS_KEY is not used because
that provider's free plan blocks the current season.

Start the backend:

```sh
.venv/bin/python -m uvicorn courtside.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173. The backend collects news and stats daily at 6 AM
Eastern while running. If started after 6 AM, it checks whether today's
collection is needed. Daily attempts are saved in the database, including failures.
Public news refreshes are disabled in scheduled mode. Reload reads saved data.

The investigator uses rules by default. For optional LLM calls, configure
LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY, set ENABLE_LLM_CALLS=true, and change
provider to openai-compatible in config/investigation.json. ENABLE_SAMPLE_AI=true enables
the separate fictional AI demo. Leave both disabled to avoid model requests.

```sh
.venv/bin/python -m unittest discover -s tests
npm --prefix frontend test
npm --prefix frontend run build
```
