# Deployment Guide

Backend → **Render** (Docker Web Service + PostgreSQL)
Frontend → **Vercel** (Static + Edge Rewrites)

---

## AI Provider

The app supports two AI providers. **You only need one key.** Selection is controlled by a single env var — no code changes required.

| `SYNTHESIS_PROVIDER` | Required key | Model used |
|---|---|---|
| `anthropic` *(default)* | `ANTHROPIC_API_KEY` | claude-sonnet-4-6 |
| `openai` | `OPENAI_API_KEY` | gpt-4o |

Set `SYNTHESIS_PROVIDER=openai` and supply `OPENAI_API_KEY` to switch to OpenAI. The app will use whichever provider is configured and ignore the other key entirely.

---

## Step 1 — PostgreSQL Database (Render or Neon)

Use either Render’s PostgreSQL or [Neon](https://neon.tech) (serverless Postgres). You only need one.

### Option A — Render PostgreSQL

1. Go to [render.com](https://render.com) → **New → PostgreSQL**
2. Configure name, region, plan (Free or paid).
3. After creation, copy the **Internal Database URL** and use it as `DATABASE_URL` (or link it via **Environment → Link a Database** so Render injects it).

### Option B — Neon

1. Create a project at [neon.tech](https://neon.tech) and create a database.
2. Copy the **connection string** from the Neon dashboard (e.g. `postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require`).
3. In Render, set `DATABASE_URL` to this string. Neon often requires `?sslmode=require` — include it if your URL doesn’t already have it.

---

## Step 2 — Deploy Backend to Render

### Create a Web Service

1. Go to [render.com](https://render.com) → **New → Web Service**
2. Connect your GitHub repo
3. Configure:

| Setting | Value |
|---|---|
| **Environment** | **Docker** |
| **Dockerfile Path** | `docker/Dockerfile` |
| **Docker Context** | `.` (repo root) |
| **Root Directory** | Leave **empty** (repo root). Render builds from the connected repo; the Dockerfile path is relative to that. |
| **Build Command** | Leave **empty**. The Dockerfile defines the build (`COPY` + `pip install`). |
| **Instance Type** | Starter ($7/mo) or higher |

Render will build the image from the Dockerfile and run the container. The app listens on the port Render assigns (the Dockerfile uses the `PORT` env var).

### Environment Variables (Render)

Set these under **Environment → Environment Variables**:

| Variable | Required | Example / Notes |
|---|---|---|
| `DATABASE_URL` | **Yes** | Internal Database URL from Step 1 |
| `JWT_SECRET_KEY` | **Yes** | Any long random string, e.g. `openssl rand -hex 32` |
| `SYNTHESIS_PROVIDER` | No | `anthropic` (default) or `openai` |
| `ANTHROPIC_API_KEY` | If using Anthropic | `sk-ant-api03-...` |
| `OPENAI_API_KEY` | If using OpenAI | `sk-proj-...` |
| `ADMIN_USERNAME` | No | Default: `admin` — change this |
| `ADMIN_PASSWORD` | **Yes** | Change from the default `changeme` |
| `INTERNAL_SECRET` | **Yes** | Random string for the nightly cron — `openssl rand -hex 32` |
| `FRONTEND_URL` | **Yes** | Your Vercel URL, e.g. `https://trading-copilot.vercel.app` |

> `FRONTEND_URL` is used for CORS. If omitted, the browser will block all API calls from the Vercel frontend.
>
> Render automatically injects `DATABASE_URL` if you link the database to your web service via **Environment → Link a Database**. Use this instead of pasting the URL manually — it stays updated if credentials rotate.

After your first deploy, note your Render service URL:
```
https://YOUR_APP_NAME.onrender.com
```
You'll need it in the next step.

---

## Step 3 — Deploy Frontend to Vercel

### Update `vercel.json`

Before deploying, open `frontend/vercel.json` and replace the placeholder with your actual Render URL:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://YOUR_APP_NAME.onrender.com/:path*"
    },
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

The first rule proxies all `/api/*` requests to Render (stripping the `/api` prefix).
The second rule makes React Router work — any unknown path serves `index.html`.

### Create a Vercel Project

1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Import your GitHub repo
3. Configure:

| Setting | Value |
|---|---|
| **Root Directory** | `frontend` |
| **Framework Preset** | Vite |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |

### Environment Variables (Vercel)

The frontend has **no required environment variables** — all API calls go through Vercel's edge rewrites defined in `vercel.json`. No `VITE_*` vars needed.

### Deploy

Click **Deploy**. Vercel will build the Vite app and publish it.

---

## Step 4 — Configure GitHub Actions (Nightly Refresh)

The nightly digest job is defined in `.github/workflows/nightly_refresh.yml`. It calls your Render backend after market close (5 PM ET, weekdays).

Add these **Repository Secrets** under **Settings → Secrets → Actions**:

| Secret | Value |
|---|---|
| `API_URL` | Your Render URL: `https://YOUR_APP_NAME.onrender.com` |
| `INTERNAL_SECRET` | Same value as the `INTERNAL_SECRET` env var on Render |

To test it manually: **Actions → Nightly Watchlist Refresh → Run workflow**.

---

## Environment Variable Summary

### Render (Backend) — full list

```
DATABASE_URL=postgresql://...          # from Render PostgreSQL (use "Link a Database")
JWT_SECRET_KEY=<random 32+ char string>
SYNTHESIS_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=                        # leave blank if using Anthropic
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<your secure password>
INTERNAL_SECRET=<random 32+ char string>
FRONTEND_URL=https://YOUR_APP.vercel.app
```

### Vercel (Frontend)

No environment variables required.

### GitHub Actions Secrets

```
API_URL=https://YOUR_APP_NAME.onrender.com
INTERNAL_SECRET=<same value as Render>
```

---

## Deployment Checklist

- [ ] Render PostgreSQL database created and linked to Web Service
- [ ] `DATABASE_URL` set (or linked via Render dashboard)
- [ ] `JWT_SECRET_KEY` set to a strong random value (not the dev default)
- [ ] `ADMIN_PASSWORD` changed from `changeme`
- [ ] `INTERNAL_SECRET` set (same value on Render and in GitHub secrets)
- [ ] `FRONTEND_URL` on Render matches your exact Vercel domain
- [ ] `vercel.json` updated with your Render URL
- [ ] GitHub Actions secrets `API_URL` and `INTERNAL_SECRET` configured
- [ ] First deploy succeeds — verify `/health` returns `{"status":"ok"}`
- [ ] Login works with your admin credentials
- [ ] AI synthesis works — search a ticker and confirm the narrative streams

---

## Local Development

```bash
# Copy and fill in your keys
cp .env.example .env        # if it exists, otherwise set vars in shell

# Start everything (PostgreSQL + API + frontend)
./scripts/build.sh up

# Frontend: http://localhost:5173
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs
```

The local stack uses PostgreSQL via Docker Compose — no SQLite, same DB engine as production.
