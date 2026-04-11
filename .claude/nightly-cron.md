# Nightly Chain Scan + Rate Limit Handling

## Goal

Run the chain scanner via the existing nightly cron job so the frontend
serves cached results (no live yfinance calls). Add rate limit throttling
to the provider. Add a cached signals endpoint for the frontend.

---

## Task 1: Add throttle to YFinanceProvider

Modify `app/services/options/chain_scanner/providers/yfinance_provider.py`:

Add a delay between yfinance API calls to avoid rate limiting.

```python
import time

class YFinanceProvider(ChainProvider):

    def __init__(self, delay: float = 1.0):
        self._delay = delay
        self._last_call = 0.0

    def _throttle(self):
        """Wait if needed to respect rate limits."""
        elapsed = time.time() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_call = time.time()
```

Add `self._throttle()` as the first line in `get_spot()`, `get_chain()`,
`get_history()`, and `get_risk_free_rate()`.

For the nightly cron (not user-facing), a 1-second delay per call is fine.
For live scans from the frontend, use `delay=0.5` via config.

**Acceptance:** No yfinance 429 errors during a 20-ticker scan.

## Task 2: Create nightly scan function

Create `app/services/options_digest.py`:

```python
"""
Nightly options chain scan.

Called from run_nightly_refresh() after equity data is fresh.
Scans all watchlisted tickers once, stores signals in option_signals.
"""
import logging
import time
from datetime import datetime, timezone

from app.database import get_db

logger = logging.getLogger(__name__)


def run_nightly_chain_scan() -> dict:
    start = time.time()

    conn = get_db()
    ticker_rows = conn.execute(
        "SELECT DISTINCT ticker_symbol FROM watchlists"
    ).fetchall()
    user_rows = conn.execute(
        "SELECT user_id, ticker_symbol FROM watchlists"
    ).fetchall()
    conn.close()

    tickers = [r["ticker_symbol"] for r in ticker_rows]
    if not tickers:
        return {"options_signals": 0, "options_tickers": 0, "options_errors": 0}

    # Build user → tickers map
    user_tickers: dict[int, set[str]] = {}
    for r in user_rows:
        user_tickers.setdefault(r["user_id"], set()).add(r["ticker_symbol"])

    # Scan once with throttled provider
    from app.services.options.chain_scanner import scan_watchlist
    from app.services.options.chain_scanner.providers import create_provider

    provider = create_provider()  # CachedProvider wraps YFinanceProvider
    signals = []
    errors = 0

    try:
        signals = scan_watchlist(tickers, provider=provider)
    except Exception as e:
        logger.error("Nightly chain scan failed: %s", e)
        errors = 1

    # Store per user
    if signals:
        conn = get_db()
        for user_id, watched in user_tickers.items():
            for s in signals:
                if s.ticker not in watched:
                    continue
                try:
                    conn.execute("""
                        INSERT INTO option_signals
                        (user_id, ticker, strike, expiry, option_type, dte,
                         spot, bid, ask, mid, open_interest, bid_ask_spread_pct,
                         chain_iv, iv_rank, iv_percentile, iv_regime,
                         garch_vol, theo_price, edge_pct, direction,
                         delta, gamma, theta, vega, conviction)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        user_id, s.ticker, s.strike, s.expiry, s.option_type,
                        s.dte, s.spot, s.bid, s.ask, s.mid, s.open_interest,
                        s.bid_ask_spread_pct, s.chain_iv, s.iv_rank,
                        s.iv_percentile, s.iv_regime, s.garch_vol,
                        s.theo_price, s.edge_pct, s.direction,
                        s.delta, s.gamma, s.theta, s.vega, s.conviction,
                    ))
                except Exception:
                    errors += 1
        conn.commit()
        conn.close()

    return {
        "options_signals": len(signals),
        "options_tickers": len(tickers),
        "options_errors": errors,
        "options_duration": round(time.time() - start, 1),
    }
```

## Task 3: Wire into nightly refresh

Modify `app/services/digest.py` — add at the end of `run_nightly_refresh()`,
before the return statement:

```python
    # Options chain scan (after equity data is fresh)
    options_result = {}
    try:
        from app.services.options_digest import run_nightly_chain_scan
        options_result = run_nightly_chain_scan()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Nightly options scan failed: %s", e)
        options_result = {"options_signals": 0, "options_errors": 1}

    return {
        "tickers_refreshed": len(tickers) - refresh_errors,
        "users_notified": len(user_ids),
        "duration_seconds": round(time.time() - start, 1),
        **options_result,
    }
```

## Task 4: Add cached signals endpoint

Add to `app/routers/chain_scan.py`:

```python
@router.get("/chain-signals")
def get_cached_signals(
    ticker: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Return latest nightly chain scan results from DB. No live yfinance calls."""
    db = get_db()
    try:
        if ticker:
            rows = db.execute("""
                SELECT * FROM option_signals
                WHERE user_id = %s AND ticker = %s
                ORDER BY scanned_at DESC, conviction DESC
                LIMIT %s
            """, (user["id"], ticker.upper(), top)).fetchall()
        else:
            # Get most recent scan batch
            rows = db.execute("""
                SELECT * FROM option_signals
                WHERE user_id = %s
                AND scanned_at >= (
                    SELECT MAX(scanned_at) - INTERVAL '1 minute'
                    FROM option_signals WHERE user_id = %s
                )
                ORDER BY conviction DESC
                LIMIT %s
            """, (user["id"], user["id"], top)).fetchall()

        last_scan = db.execute("""
            SELECT MAX(scanned_at) as last_scan
            FROM option_signals WHERE user_id = %s
        """, (user["id"],)).fetchone()
    finally:
        db.close()

    return {
        "signals": [dict(r) for r in rows],
        "total": len(rows),
        "last_scan": str(last_scan["last_scan"]) if last_scan and last_scan["last_scan"] else None,
    }
```

## Task 5: Frontend — load cached on mount

Update `ChainScannerPanel.tsx`:

1. On mount, call `GET /options/chain-signals` (fast, no yfinance)
2. Display cached results with "Last scanned: ..." timestamp
3. "Scan Now" button calls `GET /options/chain-scan` (live, slower)
4. Add `getCachedSignals()` to `api/client.ts`

## Task 6: Update CHANGELOG

---

## Files

| Action | File |
|--------|------|
| CREATE | `app/services/options_digest.py` |
| CREATE | `tests/test_options_digest.py` |
| MODIFY | `app/services/options/chain_scanner/providers/yfinance_provider.py` — add throttle |
| MODIFY | `app/services/digest.py` — call nightly chain scan |
| MODIFY | `app/routers/chain_scan.py` — add /options/chain-signals endpoint |
| MODIFY | `frontend/src/api/client.ts` — add getCachedSignals() |
| MODIFY | `frontend/src/components/ChainScannerPanel.tsx` — load cached on mount |
| MODIFY | `CHANGELOG.md` |
