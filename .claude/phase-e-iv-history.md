# Phase E — Historical IV Tracking

## Goal

Store daily ATM IV snapshots so the chain scanner computes real IV rank
from actual implied volatility history instead of the realized-vol proxy.
After 30+ days of data, signal quality improves significantly.

---

## DB table

Add to `app/database.py`:

```sql
CREATE TABLE IF NOT EXISTS iv_history (
    id               SERIAL PRIMARY KEY,
    ticker           TEXT NOT NULL,
    scan_date        DATE NOT NULL,
    atm_iv_call      DOUBLE PRECISION,
    atm_iv_put       DOUBLE PRECISION,
    atm_iv_avg       DOUBLE PRECISION,
    realized_vol_30d DOUBLE PRECISION,
    spot             DOUBLE PRECISION,
    UNIQUE (ticker, scan_date)
);

CREATE INDEX IF NOT EXISTS idx_iv_history_ticker_date
    ON iv_history(ticker, scan_date DESC);
```

## Nightly job

In the nightly chain scan function, after scanning each ticker:
1. Extract ATM call IV and ATM put IV from the chain snapshot
2. Compute average: `(atm_iv_call + atm_iv_put) / 2`
3. Store realized_vol_30d from history data
4. INSERT OR UPDATE (upsert on `ticker, scan_date`)

```python
conn.execute("""
    INSERT INTO iv_history (ticker, scan_date, atm_iv_call, atm_iv_put, atm_iv_avg, realized_vol_30d, spot)
    VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s)
    ON CONFLICT (ticker, scan_date) DO UPDATE
    SET atm_iv_call = EXCLUDED.atm_iv_call,
        atm_iv_put = EXCLUDED.atm_iv_put,
        atm_iv_avg = EXCLUDED.atm_iv_avg,
        realized_vol_30d = EXCLUDED.realized_vol_30d,
        spot = EXCLUDED.spot
""", (ticker, atm_iv_call, atm_iv_put, atm_iv_avg, rv_30d, spot))
```

## Upgrade iv_rank.py

Add a second code path in `compute_iv_metrics()`:

```python
def compute_iv_metrics(current_iv, history, iv_history_rows=None):
    if iv_history_rows and len(iv_history_rows) >= 30:
        # Use actual IV history — more accurate
        historical_ivs = [r["atm_iv_avg"] for r in iv_history_rows]
        iv_min = min(historical_ivs)
        iv_max = max(historical_ivs)
        iv_rank = (current_iv - iv_min) / (iv_max - iv_min) * 100
        iv_percentile = sum(1 for iv in historical_ivs if iv < current_iv) / len(historical_ivs) * 100
        # ... same regime classification
    else:
        # Fallback to realized-vol proxy (existing behavior)
        # ... existing code
```

The scanner orchestrator queries `iv_history` before calling
`compute_iv_metrics` and passes the rows if available.

## API endpoint

```
GET /options/iv-history/{ticker}?days=365
```

Returns daily IV history for charting:
```json
{
  "ticker": "AAPL",
  "history": [
    {"date": "2026-04-10", "atm_iv": 0.285, "rv_30d": 0.234, "spot": 255.92},
    ...
  ],
  "current_rank": 78.5,
  "current_percentile": 82.3
}
```

## Frontend

Add an IV rank chart to the chain scanner signal cards:
- Sparkline showing 1-year IV history
- Current IV rank highlighted
- "IV rank based on X days of history" label
- After 30 days: badge showing "Real IV" vs "Proxy IV"

## Tests

- Upsert inserts new row, updates on conflict
- IV rank with 60+ days of real data matches expected values
- Fallback to proxy when <30 days of history
- API endpoint returns correct shape

## Files

| Action | File |
|--------|------|
| CREATE | `tests/test_iv_history.py` |
| MODIFY | `app/database.py` — add iv_history table |
| MODIFY | `app/services/options/chain_scanner/iv_rank.py` — add real IV path |
| MODIFY | `app/services/options/chain_scanner/scanner.py` — query iv_history |
| MODIFY | `app/routers/chain_scan.py` — add /options/iv-history endpoint |
| MODIFY | `app/services/digest.py` — store IV snapshot nightly |
| MODIFY | `frontend/src/components/ChainScannerPanel.tsx` — IV chart |
| MODIFY | `CHANGELOG.md` |
