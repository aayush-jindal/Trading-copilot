# Trading Copilot

A self-hosted stock analysis tool that combines technical analysis with AI-generated narrative synthesis. Search any ticker, get TA signals across trend, momentum, volatility, volume, and support/resistance — then stream a plain-English copilot narrative powered by Claude or GPT-4o.

![Trading Copilot](trading_copilot_logo.png)

---

## Features

- **Candlestick chart** with SMA 20/50/200 and Bollinger Bands overlays
- **8-cell signal panel** — trend, RSI, MACD, Stochastic, Bollinger Bands, ATR, volume, support/resistance
- **AI narrative** — streams a concise, analyst-style synthesis via SSE (Anthropic Claude or OpenAI GPT-4o)
- **Watchlist** — add tickers, view a dashboard of current price + day change + trend signal
- **Nightly digest** — GitHub Actions cron refreshes watchlist data after market close and delivers per-user digest notifications
- **JWT authentication** — login/signup, all routes protected
- **Dual AI provider** — switch between Anthropic and OpenAI with a single environment variable

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |
| Charts | TradingView Lightweight Charts v4 |
| Backend | FastAPI (Python 3.11) |
| Database | PostgreSQL (psycopg2) |
| AI | Anthropic Claude (`claude-sonnet-4-6`) or OpenAI GPT-4o |
| Auth | JWT (python-jose + bcrypt) |
| Market data | yfinance |
| TA indicators | TA-Lib + ta + scipy |
| Infra | Docker Compose (local), Render (backend), Vercel (frontend) |

---

## Quick Start — Local Development

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- An Anthropic **or** OpenAI API key

### 1. Clone the repo

```bash
git clone https://github.com/your-org/trading-copilot.git
cd trading-copilot
```

### 2. Set environment variables

Create a `.env` file in the project root (the same directory as `docker/`):

```bash
# Required — pick one AI provider
ANTHROPIC_API_KEY=sk-ant-api03-...
# OPENAI_API_KEY=sk-proj-...
# SYNTHESIS_PROVIDER=openai   # uncomment to use OpenAI instead

# Required for JWT signing
JWT_SECRET_KEY=change-me-to-a-random-string

# Optional — change admin credentials
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
```

### 3. Start everything

```bash
./scripts/build.sh up
```

This starts three containers:
- `db` — PostgreSQL 16
- `api` — FastAPI on port 8000 (with hot reload)
- `frontend` — Vite dev server on port 5173

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

### 4. Log in

Default credentials: `admin` / `changeme`

Change these via the `ADMIN_USERNAME` / `ADMIN_PASSWORD` environment variables.

---

## Project Structure

```
trading-copilot/
├── app/                        # FastAPI backend
│   ├── routers/
│   │   ├── auth.py             # POST /auth/login, POST /auth/register
│   │   ├── data.py             # GET /data/{ticker}/latest
│   │   ├── analysis.py         # GET /analyze/{ticker}
│   │   ├── synthesis.py        # GET /synthesize/{ticker}  (SSE)
│   │   ├── watchlist.py        # CRUD /watchlist
│   │   ├── notifications.py    # GET /notifications
│   │   └── internal.py         # POST /internal/refresh-watchlist
│   ├── services/
│   │   ├── market_data.py      # yfinance fetch + staleness cache
│   │   ├── ta_engine.py        # TA signal computation
│   │   ├── ai_engine.py        # AI narrative + daily cache
│   │   ├── auth.py             # JWT + bcrypt helpers
│   │   └── digest.py           # Nightly digest generator
│   ├── config.py               # All environment variables
│   ├── database.py             # PostgreSQL connection + schema init
│   ├── dependencies.py         # FastAPI dependency injection (get_current_user)
│   ├── main.py                 # App factory + CORS + router registration
│   └── models.py               # Pydantic response models
├── frontend/
│   └── src/
│       ├── api/client.ts       # All API calls (fetch + SSE)
│       ├── context/
│       │   └── AuthContext.tsx # JWT stored in localStorage
│       ├── pages/
│       │   ├── AnalysisPage.tsx
│       │   ├── WatchlistPage.tsx
│       │   ├── LoginPage.tsx
│       │   └── SignupPage.tsx
│       └── components/
│           ├── PriceChart.tsx
│           ├── SignalPanel.tsx
│           ├── NarrativePanel.tsx
│           └── NotificationsPanel.tsx
├── tests/                      # pytest — 46 tests
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml      # Local stack (db + api + frontend)
├── scripts/
│   └── build.sh                # Developer CLI
├── .github/workflows/
│   └── nightly_refresh.yml     # Nightly cron (5pm ET weekdays)
└── DEPLOYMENT.md               # Full Render + Vercel guide
```

---

## API Reference

All endpoints except `/health`, `/auth/login`, and `/auth/register` require a `Authorization: Bearer <token>` header.

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | OAuth2 password form → JWT |
| `POST` | `/auth/register` | JSON body → JWT |

### Market Data

| Method | Path | Description |
|---|---|---|
| `GET` | `/data/{ticker}/latest?days=365` | OHLCV price history + ticker info |

### Technical Analysis

| Method | Path | Description |
|---|---|---|
| `GET` | `/analyze/{ticker}` | Full TA signal set (trend, momentum, volatility, volume, S/R, candlestick) |

### AI Synthesis

| Method | Path | Description |
|---|---|---|
| `GET` | `/synthesize/{ticker}` | SSE stream — analyst narrative (cached per ticker per UTC day) |

### Watchlist

| Method | Path | Description |
|---|---|---|
| `GET` | `/watchlist` | List user's watchlist |
| `POST` | `/watchlist/{ticker}` | Add ticker |
| `DELETE` | `/watchlist/{ticker}` | Remove ticker |
| `GET` | `/watchlist/dashboard` | Price + day change + trend signal per ticker |

### Notifications

| Method | Path | Description |
|---|---|---|
| `GET` | `/notifications` | Latest 50 notifications |
| `PATCH` | `/notifications/{id}/read` | Mark one as read |
| `PATCH` | `/notifications/read-all` | Mark all as read |

### Internal (cron use only)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/internal/refresh-watchlist` | `INTERNAL_SECRET` bearer | Refresh all watchlisted tickers + generate digests |

---

## AI Provider Configuration

No code changes are needed to switch providers. Set one environment variable:

| `SYNTHESIS_PROVIDER` | Required key | Model |
|---|---|---|
| `anthropic` *(default)* | `ANTHROPIC_API_KEY` | claude-sonnet-4-6 |
| `openai` | `OPENAI_API_KEY` | gpt-4o |

---

## Developer Scripts

```bash
./scripts/build.sh build          # Rebuild the api Docker image
./scripts/build.sh up             # Start db + api + frontend
./scripts/build.sh down           # Stop all containers
./scripts/build.sh restart        # Restart all containers
./scripts/build.sh test           # Run pytest inside the api container
./scripts/build.sh logs           # Tail logs for all containers
./scripts/build.sh logs-api       # Tail api logs only
./scripts/build.sh logs-frontend  # Tail frontend (Vite) logs only
```

### Running tests

```bash
./scripts/build.sh test
# 46 tests — ai_engine, analysis_endpoint, synthesis_endpoint, ta_engine
```

---

## Deployment

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for the full step-by-step guide covering:

- Render (Docker Web Service + PostgreSQL)
- Vercel (Vite static site + edge rewrites)
- GitHub Actions nightly cron setup
- All required environment variables

**Short version:**

1. Create a Render PostgreSQL database
2. Deploy backend as a Docker Web Service on Render — link the database
3. Deploy frontend on Vercel — set root directory to `frontend/`, update `vercel.json` with your Render URL
4. Add `API_URL` and `INTERNAL_SECRET` as GitHub repository secrets for the nightly cron

---

## Environment Variables

### Backend (Render / Docker)

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | `dev-secret-...` | Random string for JWT signing |
| `SYNTHESIS_PROVIDER` | No | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | If using Anthropic | — | `sk-ant-api03-...` |
| `OPENAI_API_KEY` | If using OpenAI | — | `sk-proj-...` |
| `ADMIN_USERNAME` | No | `admin` | Default admin username |
| `ADMIN_PASSWORD` | Yes | `changeme` | Change this before deploying |
| `INTERNAL_SECRET` | Yes | — | Bearer token for cron endpoint |
| `FRONTEND_URL` | Yes | — | Vercel URL (used for CORS) |

### Frontend (Vercel)

No environment variables required. All API calls are proxied through `vercel.json` rewrites.

---

## License

Copyright (c) 2026 RASIK LABS

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

## Contributor License Agreement (CLA)

All contributions require acceptance of the Rasik Labs Contributor License Agreement (CLA).

By submitting a pull request, you agree to grant Rasik Labs the right to relicense your contributions under both open-source and commercial licenses.


