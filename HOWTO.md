# Trading Copilot — How to Run

## Quick start

```bash
cp .env.example .env          # fill in your API keys
./scripts/build.sh build      # build Docker images (first time only)
./scripts/build.sh up         # start all services
```

Open **http://localhost:5173** in your browser.

---

## Prerequisites

- Docker + Docker Compose
- An Anthropic API key (required for AI narrative)
- An OpenAI API key (required for book strategy RAG)

---

## Environment variables

Create a `.env` file in the project root. All variables are optional except the API keys.

```env
# ── AI providers ──────────────────────────────────────────────────────────────

# Required for AI narrative (SSE stream on analysis page)
ANTHROPIC_API_KEY=sk-ant-...

# Required for knowledge base embeddings + book strategy generation
OPENAI_API_KEY=sk-...

# Which provider generates the narrative. Default: anthropic
# Options: anthropic | openai
SYNTHESIS_PROVIDER=anthropic

# ── Auth ──────────────────────────────────────────────────────────────────────

# Login credentials. Defaults shown — change for any shared/production use.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme

# JWT signing secret. MUST be changed in production.
JWT_SECRET_KEY=dev-secret-change-in-production

# ── Production only ───────────────────────────────────────────────────────────

# Allowed CORS origin for the hosted frontend (leave blank for local dev)
FRONTEND_URL=https://your-frontend.onrender.com

# Secret for internal scheduler endpoints (leave blank to disable)
INTERNAL_SECRET=

# ── Database (set automatically by Docker — only override if running outside Docker)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/trading_copilot
```

---

## build.sh commands

Run all commands from the project root:

```bash
./scripts/build.sh build          # build Docker images
./scripts/build.sh up             # start all services in background
./scripts/build.sh down           # stop all services
./scripts/build.sh restart        # down then up
./scripts/build.sh logs           # tail logs from all services
./scripts/build.sh logs-api       # tail API logs only
./scripts/build.sh logs-frontend  # tail frontend logs only
./scripts/build.sh test           # run pytest inside the API container
```

---

## Services and ports

| Service  | Port | URL |
|----------|------|-----|
| Frontend | 5173 | http://localhost:5173 |
| API      | 8000 | http://localhost:8000 |
| API docs | 8000 | http://localhost:8000/docs |
| Database | 5432 | postgres:postgres@localhost:5432/trading_copilot |

---

## Smoke test

Verifies the full API surface is working end-to-end:

```bash
docker exec docker-api-1 python scripts/smoke_test.py
```

Expected: `33/33 checks passed`

---

## Knowledge base (RAG)

Books live in `resources/`. Drop PDFs there, then run ingest inside the container:

```bash
# Ingest all PDFs in resources/
docker exec docker-api-1 python -m tools.knowledge_base.run ingest

# Ingest from a custom path
docker exec docker-api-1 python -m tools.knowledge_base.run ingest --resources /path/to/pdfs

# Check what's been indexed
docker exec docker-api-1 python -m tools.knowledge_base.run status

# Test a query manually (without going through the UI)
docker exec docker-api-1 python -m tools.knowledge_base.run query --ticker AAPL
docker exec docker-api-1 python -m tools.knowledge_base.run query --ticker AAPL --top-k 12
```

The `📚 Generate book analysis` button in the UI calls this automatically. Results are cached per ticker per day in the database.

### RAG settings (tools/knowledge_base/config.py)

| Setting | Default | Description |
|---------|---------|-------------|
| `EMBED_MODEL` | `text-embedding-3-small` | OpenAI embedding model (1536 dims) |
| `CHUNK_SIZE` | 1500 | Characters per chunk (~400 tokens) |
| `CHUNK_OVERLAP` | 200 | Character overlap between chunks |
| `TOP_K_RETRIEVAL` | 8 | Book passages sent to Claude per query |
| `RESOURCES_DIR` | `resources/` | Where to look for PDFs |

---

## Running tests

```bash
# All tests
./scripts/build.sh test

# Specific file
docker exec docker-api-1 pytest tests/test_ta_engine.py -v

# With output
docker exec docker-api-1 pytest tests/ -v -s
```

---

## Backtesting

Run a backtest on a ticker (results printed to stdout):

```bash
docker exec docker-api-1 python backtesting/run_backtest.py --ticker SPY --years 5
```

---

## Rebuilding after code changes

The API container mounts `app/`, `backtesting/`, and `tools/` as live volumes — Python changes take effect immediately via `--reload`.

Frontend changes (`.tsx`, `.ts`, `.css`) are also hot-reloaded by Vite.

Only rebuild the image if you change `requirements.txt` or `Dockerfile`:

```bash
./scripts/build.sh build
./scripts/build.sh restart
```

---

## Production deployment (Render)

1. Set all env vars in the Render service dashboard (especially `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `JWT_SECRET_KEY`, `FRONTEND_URL`)
2. Set `DATABASE_URL` to your Render Postgres connection string
3. To seed the knowledge base in production, export local chunks and import:

```bash
# Export from local Docker
docker exec docker-db-1 pg_dump -U postgres -t knowledge_chunks trading_copilot > docker/knowledge_chunks.sql

# Import to Render DB
psql $RENDER_DATABASE_URL < docker/knowledge_chunks.sql
```
