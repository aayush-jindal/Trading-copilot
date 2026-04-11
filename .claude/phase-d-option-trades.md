# Phase D — Options Trade Tracker

## Goal

Add options position tracking to the existing trade tracker. A user can
"open" a trade from a chain scan signal, track live P&L (repriced via BS),
and close with exit reason. Integrates with the nightly refresh for
automated exit alerts.

---

## DB table

Add to `app/database.py` in `init_db()`, before `conn.commit()`:

```sql
CREATE TABLE IF NOT EXISTS option_trades (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id),
    ticker           TEXT NOT NULL,
    strategy         TEXT NOT NULL,
    is_credit        BOOLEAN NOT NULL DEFAULT FALSE,
    legs             JSONB NOT NULL,
    entry_premium    DOUBLE PRECISION NOT NULL,
    exit_target      DOUBLE PRECISION,
    option_stop      DOUBLE PRECISION,
    max_profit       DOUBLE PRECISION,
    max_loss         DOUBLE PRECISION,
    spread_width     DOUBLE PRECISION,
    expiry           TEXT NOT NULL,
    dte_at_open      INTEGER NOT NULL,
    chain_iv         DOUBLE PRECISION,
    iv_rank          DOUBLE PRECISION,
    iv_regime        TEXT,
    conviction       DOUBLE PRECISION,
    status           TEXT NOT NULL DEFAULT 'open',
    entry_date       DATE NOT NULL DEFAULT CURRENT_DATE,
    exit_date        DATE,
    exit_price       DOUBLE PRECISION,
    exit_reason      TEXT,
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_option_trades_user
    ON option_trades(user_id) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_option_trades_expiry
    ON option_trades(expiry);
```

## Backend

### New file: `app/routers/option_trades.py`

Endpoints:
- `POST /option-trades/` — open a trade from a priced chain scan signal
- `GET /option-trades/` — list open option trades with live repricing
- `DELETE /option-trades/{id}` — close a trade
- `GET /option-trades/{id}/reprice` — reprice one trade at current spot/IV

### Request model (add to `app/models.py`):

```python
class OptionTradeCreate(BaseModel):
    ticker: str
    strategy: str
    is_credit: bool
    legs: list[dict]          # from priced_strategy.legs
    entry_premium: float
    exit_target: float
    option_stop: float
    max_profit: float | None = None
    max_loss: float | None = None
    spread_width: float | None = None
    expiry: str
    dte_at_open: int
    chain_iv: float | None = None
    iv_rank: float | None = None
    iv_regime: str | None = None
    conviction: float | None = None
    notes: str | None = None
```

### Response model:

```python
class OptionTradeResponse(BaseModel):
    id: int
    ticker: str
    strategy: str
    is_credit: bool
    legs: list[dict]
    entry_premium: float
    exit_target: float
    option_stop: float
    max_profit: float | None
    max_loss: float | None
    expiry: str
    dte_remaining: int          # computed from expiry - today
    entry_date: str
    status: str
    current_value: float | None # BS reprice at current spot
    current_pnl: float | None   # current_value - entry_premium (debit) or entry_premium - current_value (credit)
    pnl_pct: float | None
    exit_alert: str | None       # APPROACHING_STOP, AT_TARGET, EXPIRY_WARNING, THETA_DECAY
    conviction: float | None
    iv_regime: str | None
```

### Repricing logic:

For `GET /option-trades/`:
- Fetch current spot via `get_or_refresh_data(ticker)`
- For each leg, reprice via `price_bs(spot, strike, T_remaining, iv, option_type)`
- Sum with sign convention → current net value
- P&L = (current_value - entry_premium) for debit, (entry_premium - current_value) for credit
- Exit alerts:
  - `APPROACHING_STOP`: current loss > 80% of max_loss
  - `AT_TARGET`: current profit > 80% of max_profit (or exit target reached)
  - `EXPIRY_WARNING`: DTE remaining < 7
  - `THETA_DECAY`: DTE remaining < 14 and position is debit (losing theta)

### Register in `app/main.py`:

```python
from app.routers import option_trades
app.include_router(option_trades.router, **_auth)
```

## Frontend

### Add to `TradeTrackerPage.tsx`:

Add a tab or section below equity trades showing option trades.
Use the same table pattern but with options-specific columns:
Strategy, Legs, Entry, Current Value, P&L, DTE, Exit Alert.

### Add to `ChainScannerPanel.tsx`:

On each priced strategy card, add a "Log Trade" button that
calls `POST /option-trades/` with the signal data.

## Nightly integration

In the nightly refresh, reprice all open option trades:
- Fetch current spot for each unique ticker
- Reprice all legs
- If exit alert fires, create a notification

## Tests

- Create a trade from mock signal data
- List trades returns correct repricing
- Close trade sets status/exit_price/exit_date
- DTE remaining computed correctly
- Exit alerts fire at correct thresholds

## Files

| Action | File |
|--------|------|
| CREATE | `app/routers/option_trades.py` |
| CREATE | `tests/test_option_trades.py` |
| MODIFY | `app/models.py` — add OptionTradeCreate, OptionTradeResponse |
| MODIFY | `app/database.py` — add option_trades table |
| MODIFY | `app/main.py` — register option_trades router |
| MODIFY | `app/services/digest.py` — add nightly reprice + alerts |
| MODIFY | `frontend/src/pages/TradeTrackerPage.tsx` — add options section |
| MODIFY | `frontend/src/components/ChainScannerPanel.tsx` — add "Log Trade" button |
| MODIFY | `frontend/src/api/client.ts` — add option trade API functions |
| MODIFY | `frontend/src/types/index.ts` — add OptionTrade types |
| MODIFY | `CHANGELOG.md` |

## Frozen files (same as always)

- `app/services/options/pricing/src/**`, `bias_detector.py`, `ta_engine.py`,
  `market_data.py`, `ai_engine.py`, `synthesis.py`
