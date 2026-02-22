#!/usr/bin/env python3
"""
Trading Copilot — Backend Smoke Test
Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --url https://trading-copilot-apq1.onrender.com
    python scripts/smoke_test.py --url https://... --password your_admin_password
"""

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

# Skip SSL verification (test script only — we're hitting our own service)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_URL = "http://localhost:8000"
TEST_USER   = f"smoketest_{int(time.time())}"
TEST_PASS   = "SmokeTest999"

# ── Colour helpers ────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg): print(f"  {RED}✗{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def request(method, url, *, body=None, headers=None, timeout=60):
    """Returns (status_code, response_body_str)."""
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if body:
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        elif isinstance(body, str):
            body = body.encode()
        req.data = body
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def jget(url, token=None, timeout=60):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    status, body = request("GET", url, headers=h, timeout=timeout)
    try:
        return status, json.loads(body)
    except Exception:
        return status, body


def jpost(url, body, token=None, form=False, timeout=60):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    if form:
        h["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(body).encode()
    else:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    status, resp = request("POST", url, body=data, headers=h, timeout=timeout)
    try:
        return status, json.loads(resp)
    except Exception:
        return status, resp


def jdelete(url, token, timeout=30):
    h = {"Authorization": f"Bearer {token}"}
    status, body = request("DELETE", url, headers=h, timeout=timeout)
    try:
        return status, json.loads(body)
    except Exception:
        return status, body


# ── Test runner ───────────────────────────────────────────────────────────────

passed = 0
failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        ok(label)
        passed += 1
    else:
        fail(f"{label}  {RED}{detail}{RESET}")
        failed += 1


def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*55}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*55}{RESET}")


# ── Tests ─────────────────────────────────────────────────────────────────────

def run(base, admin_password):
    token = None

    # ── 1. Health ─────────────────────────────────────────────────────────────
    section("1 · Health Check")
    t0 = time.time()
    status, body = jget(f"{base}/health")
    elapsed = round((time.time() - t0) * 1000)
    check(f"/health → 200 ({elapsed}ms)", status == 200, f"got {status}: {body}")
    if status == 200:
        check("response is {status: ok}", body.get("status") == "ok", str(body))

    # ── 2. Auth ───────────────────────────────────────────────────────────────
    section("2 · Authentication")

    # Wrong password
    status, body = jpost(f"{base}/auth/login",
                         {"username": "admin", "password": "wrong_password_xyz"},
                         form=True)
    check("wrong password → 401", status == 401, f"got {status}: {body}")

    # No token on protected route
    status, body = jget(f"{base}/watchlist")
    check("no token → 401", status == 401, f"got {status}: {body}")

    # Register test user
    status, body = jpost(f"{base}/auth/register",
                         {"username": TEST_USER, "password": TEST_PASS})
    check(f"register new user → 201", status == 201, f"got {status}: {body}")
    if status == 201:
        token = body.get("access_token")
        check("register returns JWT", bool(token), str(body))

    # Login with new user
    if token:
        status, body = jpost(f"{base}/auth/login",
                             {"username": TEST_USER, "password": TEST_PASS},
                             form=True)
        check("login → 200", status == 200, f"got {status}: {body}")
        if status == 200:
            login_token = body.get("access_token")
            check("login returns JWT", bool(login_token), str(body))
            token = login_token  # use fresh login token

    # Duplicate username
    status, body = jpost(f"{base}/auth/register",
                         {"username": TEST_USER, "password": TEST_PASS})
    check("duplicate username → 409", status == 409, f"got {status}: {body}")

    if not token:
        fail("No token — skipping all authenticated tests")
        return

    # ── 3. Watchlist CRUD ─────────────────────────────────────────────────────
    section("3 · Watchlist CRUD")

    status, body = jget(f"{base}/watchlist", token)
    check("empty watchlist → 200 []", status == 200 and body == [], f"got {status}: {body}")

    status, body = jpost(f"{base}/watchlist/AAPL", {}, token)
    check("add AAPL → 201", status == 201, f"got {status}: {body}")

    status, body = jpost(f"{base}/watchlist/MSFT", {}, token)
    check("add MSFT → 201", status == 201, f"got {status}: {body}")

    # Add duplicate — should be idempotent
    status, body = jpost(f"{base}/watchlist/AAPL", {}, token)
    check("add AAPL duplicate → idempotent (201)", status == 201, f"got {status}: {body}")

    status, body = jget(f"{base}/watchlist", token)
    symbols = [r["ticker_symbol"] for r in body] if isinstance(body, list) else []
    check("watchlist has AAPL + MSFT", set(symbols) == {"AAPL", "MSFT"}, f"got {symbols}")

    status, body = jdelete(f"{base}/watchlist/MSFT", token)
    check("remove MSFT → 200", status == 200, f"got {status}: {body}")

    status, body = jdelete(f"{base}/watchlist/NOTINLIST", token)
    check("remove non-existent → 404", status == 404, f"got {status}: {body}")

    status, body = jget(f"{base}/watchlist", token)
    symbols = [r["ticker_symbol"] for r in body] if isinstance(body, list) else []
    check("watchlist now only AAPL", symbols == ["AAPL"], f"got {symbols}")

    # ── 4. Notifications ──────────────────────────────────────────────────────
    section("4 · Notifications")
    status, body = jget(f"{base}/notifications", token)
    check("notifications → 200 list", status == 200 and isinstance(body, list),
          f"got {status}: {body}")

    # ── 5. Market Data ────────────────────────────────────────────────────────
    section("5 · Market Data  (hits yfinance — may be slow)")

    info("fetching AAPL data (up to 60s)...")
    t0 = time.time()
    status, body = jget(f"{base}/data/AAPL/latest?days=5", token, timeout=90)
    elapsed = round(time.time() - t0, 1)
    check(f"GET /data/AAPL/latest → 200 ({elapsed}s)", status == 200,
          f"got {status}: {str(body)[:300]}")
    if status == 200:
        prices = body.get("prices", [])
        check(f"returned ≤5 price rows (got {len(prices)})", 0 < len(prices) <= 5, str(prices[:1]))
        if prices:
            row = prices[0]
            check("price row has open/high/low/close/volume",
                  all(k in row for k in ("open", "high", "low", "close", "volume")),
                  str(row))
    else:
        warn(f"Detail: {str(body)[:400]}")

    info("fetching invalid ticker XYZNOTREAL999...")
    status, body = jget(f"{base}/data/XYZNOTREAL999", token, timeout=30)
    check("invalid ticker → 404", status == 404,
          f"got {status}: {str(body)[:200]}")
    if status == 500:
        warn(f"Detail (use this to debug): {str(body)[:400]}")

    # ── 6. Technical Analysis ─────────────────────────────────────────────────
    section("6 · Technical Analysis")

    info("running TA on AAPL (uses cached data)...")
    t0 = time.time()
    status, body = jget(f"{base}/analyze/AAPL", token, timeout=90)
    elapsed = round(time.time() - t0, 1)
    check(f"GET /analyze/AAPL → 200 ({elapsed}s)", status == 200,
          f"got {status}: {str(body)[:300]}")
    if status == 200:
        for section_key in ("trend", "momentum", "volatility", "volume", "support_resistance"):
            check(f"  has '{section_key}'", section_key in body, str(list(body.keys())))
        trend = body.get("trend", {})
        check(f"  trend.signal is BULLISH/BEARISH/NEUTRAL",
              trend.get("signal") in ("BULLISH", "BEARISH", "NEUTRAL"),
              str(trend.get("signal")))
    else:
        warn(f"Detail: {str(body)[:400]}")

    # ── 7. Watchlist Dashboard ────────────────────────────────────────────────
    section("7 · Watchlist Dashboard")

    info("loading dashboard (fetches price + TA per ticker)...")
    t0 = time.time()
    status, body = jget(f"{base}/watchlist/dashboard", token, timeout=120)
    elapsed = round(time.time() - t0, 1)
    check(f"GET /watchlist/dashboard → 200 ({elapsed}s)", status == 200,
          f"got {status}: {str(body)[:300]}")
    if status == 200 and isinstance(body, list) and body:
        item = body[0]
        check("dashboard item has ticker_symbol + price + trend_signal",
              all(k in item for k in ("ticker_symbol", "price", "trend_signal")),
              str(item))

    # ── 8. AI Synthesis (SSE) ─────────────────────────────────────────────────
    section("8 · AI Synthesis  (SSE stream — requires API key)")

    info("opening SSE stream for AAPL (30s timeout)...")
    req = urllib.request.Request(f"{base}/synthesize/AAPL")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            ct = resp.headers.get("Content-Type", "")
            check("content-type: text/event-stream", "text/event-stream" in ct, ct)
            first_chunk = resp.read(256).decode(errors="replace")
            check("received SSE data", "data:" in first_chunk, repr(first_chunk[:100]))
            if "[ERROR]" in first_chunk:
                warn(f"Stream returned error: {first_chunk}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 503:
            warn(f"503 — AI key not configured: {body}")
        else:
            check(f"SSE stream → 200", False, f"HTTP {e.code}: {body[:200]}")
    except Exception as e:
        warn(f"SSE timed out or failed: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    section("Summary")
    total = passed + failed
    colour = GREEN if failed == 0 else RED
    print(f"\n  {colour}{BOLD}{passed}/{total} checks passed{RESET}")
    if failed:
        print(f"  {RED}{failed} failed — see ✗ lines above{RESET}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trading Copilot backend smoke test")
    parser.add_argument("--url", default=DEFAULT_URL,
                        help=f"Base URL (default: {DEFAULT_URL})")
    parser.add_argument("--password", default=None,
                        help="Admin password (not required — test user is created fresh)")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    print(f"\n{BOLD}Trading Copilot — Smoke Test{RESET}")
    print(f"  Target : {CYAN}{base}{RESET}")
    print(f"  Time   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    run(base, args.password)
