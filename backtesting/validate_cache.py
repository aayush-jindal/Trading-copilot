"""
validate_cache.py — DB health check and universe pre-fetch.

Run this BEFORE every backtest run:
    python backtesting/validate_cache.py

What it does:
  1. Checks ohlcv.db integrity (PRAGMA integrity_check + table structure)
  2. Pre-fetches every ticker × window needed for the backtest
  3. Reports per-ticker row counts and flags anything with insufficient data
  4. Exits non-zero so run_backtest.py refuses to start if something is wrong

Exit codes:
  0  — all clear, safe to run backtest
  1  — DB corrupted  → delete backtesting/ohlcv.db and re-run this script
  2  — too many tickers missing data  → check network / yfinance status
"""

import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.cache import DataCache, DB_PATH
from backtesting.data import YFinanceProvider
from backtesting.run_backtest import UNIVERSE, TRAIN_START, TRAIN_END, TEST_START, TEST_END, TICKER_STARTS

MIN_TRAIN_ROWS = 200   # need at least 200 bars for signal warmup
MIN_TEST_ROWS  = 100

REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


# ── 1. DB integrity ────────────────────────────────────────────────────────────

def check_db_integrity(db_path: str = DB_PATH) -> bool:
    """Run SQLite integrity_check and verify table + index exist."""
    if not os.path.exists(db_path):
        print(f"  [INFO] No DB found at {db_path} — will be created on first fetch")
        return True

    try:
        conn = sqlite3.connect(db_path, timeout=10)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
    except Exception as e:
        print(f"  [FAIL] Cannot open DB: {e}")
        return False

    if result[0] != "ok":
        print(f"  [FAIL] integrity_check returned: {result[0]}")
        return False

    # Verify required table and columns exist
    try:
        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(ohlcv)").fetchall()}
        conn.close()
        if not REQUIRED_COLUMNS.issubset(cols):
            print(f"  [FAIL] ohlcv table missing columns: {REQUIRED_COLUMNS - cols}")
            return False
    except Exception as e:
        print(f"  [FAIL] Table check error: {e}")
        return False

    print(f"  [OK] DB integrity check passed")
    return True


# ── 2. Pre-fetch universe ──────────────────────────────────────────────────────

def prefetch_universe(provider: YFinanceProvider, cache: DataCache) -> dict:
    """
    Fetch daily data for every ticker × window.
    Returns {ticker: {"train_rows": int, "test_rows": int, "ok": bool}}
    """
    results = {}

    for ticker in UNIVERSE:
        train_start = TICKER_STARTS.get(ticker, TRAIN_START)
        status = {"train_rows": 0, "test_rows": 0, "ok": False}

        # ── train ──
        try:
            df = provider.fetch_daily(ticker, train_start, TRAIN_END)
            status["train_rows"] = len(df)
        except Exception as e:
            print(f"  [WARN] {ticker} train fetch failed: {e}")

        # ── test ──
        try:
            df = provider.fetch_daily(ticker, TEST_START, TEST_END)
            status["test_rows"] = len(df)
        except Exception as e:
            print(f"  [WARN] {ticker} test fetch failed: {e}")

        status["ok"] = (
            status["train_rows"] >= MIN_TRAIN_ROWS and
            status["test_rows"]  >= MIN_TEST_ROWS
        )
        results[ticker] = status

    return results


# ── 3. Report + gate ───────────────────────────────────────────────────────────

def report(results: dict) -> int:
    """Print per-ticker summary. Returns count of failed tickers."""
    failed = []
    print(f"\n  {'Ticker':<10} {'Train rows':>12} {'Test rows':>10}  Status")
    print("  " + "-" * 44)
    for ticker, s in sorted(results.items()):
        ok_str = "OK" if s["ok"] else "INSUFFICIENT"
        print(f"  {ticker:<10} {s['train_rows']:>12,} {s['test_rows']:>10,}  {ok_str}")
        if not s["ok"]:
            failed.append(ticker)

    print(f"\n  {len(results) - len(failed)}/{len(results)} tickers ready")
    if failed:
        print(f"  Insufficient data: {', '.join(failed)}")
    return len(failed)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("  BACKTEST CACHE VALIDATOR")
    print("=" * 60)

    # Step 1: DB integrity
    print("\n[1/3] Checking DB integrity...")
    if not check_db_integrity():
        print("\n  ACTION: Delete backtesting/ohlcv.db and re-run this script.")
        return 1

    # Step 2: Pre-fetch
    print(f"\n[2/3] Pre-fetching {len(UNIVERSE)} tickers...")
    print(f"  Train: {TRAIN_START} → {TRAIN_END}")
    print(f"  Test:  {TEST_START} → {TEST_END}")

    cache    = DataCache(DB_PATH)
    provider = YFinanceProvider(cache=cache)
    results  = prefetch_universe(provider, cache)

    # Step 3: Report
    print("\n[3/3] Coverage report:")
    n_failed = report(results)

    # Gate: allow up to 3 tickers with insufficient data (e.g. newly listed, delisted)
    MAX_ALLOWED_FAILURES = 3
    print("\n" + "=" * 60)
    if n_failed <= MAX_ALLOWED_FAILURES:
        print(f"  PASS — {n_failed} ticker(s) below threshold (max {MAX_ALLOWED_FAILURES} allowed)")
        print("  Safe to run: python backtesting/run_backtest.py")
        print("=" * 60)
        return 0
    else:
        print(f"  FAIL — {n_failed} tickers have insufficient data (max {MAX_ALLOWED_FAILURES} allowed)")
        print("  Check network connectivity or yfinance status, then re-run.")
        print("=" * 60)
        return 2


if __name__ == "__main__":
    sys.exit(main())
