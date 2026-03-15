# Phase 5 — Trade tracker

## Before starting
Confirm phase4.md complete checklist is fully checked off.

## Gate to advance to Phase 6
- POST /trades logs a trade to DB
- GET /trades returns user's open trades with live R calculation
- DELETE /trades/{id} closes a trade
- Nightly exit monitoring job runs without errors
- `python -m pytest tests/` still passes

---

## Task 5.1 — Add open_trades table to DB schema

READS FIRST:
- app/database.py (full file — schema init pattern)
- app/models.py (existing models)

GOAL:
Add the open_trades table. This is the only DB change in this phase.

MODIFY: app/database.py
  Add to schema init:
  ```sql
  CREATE TABLE IF NOT EXISTS open_trades (
      id              SERIAL PRIMARY KEY,
      user_id         INTEGER NOT NULL REFERENCES users(id),
      ticker          VARCHAR(10) NOT NULL,
      strategy_name   VARCHAR(50) NOT NULL,
      strategy_type   VARCHAR(20) NOT NULL,
      entry_price     NUMERIC(12,4) NOT NULL,
      stop_loss       NUMERIC(12,4) NOT NULL,
      target          NUMERIC(12,4) NOT NULL,
      shares          INTEGER NOT NULL,
      entry_date      DATE NOT NULL DEFAULT CURRENT_DATE,
      risk_reward     NUMERIC(6,3),
      status          VARCHAR(20) NOT NULL DEFAULT 'open',
      exit_price      NUMERIC(12,4),
      exit_date       DATE,
      exit_reason     VARCHAR(50),
      created_at      TIMESTAMP DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_open_trades_user
      ON open_trades(user_id) WHERE status = 'open';
  ```

MODIFY: app/models.py
  Add:
  ```python
  class TradeCreate(BaseModel):
      ticker: str
      strategy_name: str
      strategy_type: str
      entry_price: float
      stop_loss: float
      target: float
      shares: int
      risk_reward: float | None = None

  class TradeResponse(BaseModel):
      id: int
      ticker: str
      strategy_name: str
      strategy_type: str
      entry_price: float
      stop_loss: float
      target: float
      shares: int
      entry_date: str
      current_price: float | None = None
      current_r: float | None = None   # live P&L in R-multiples
      exit_alert: str | None = None    # "APPROACHING_STOP" | "AT_TARGET" | "EXIT_SIGNAL"
  ```

VERIFY:
```bash
docker compose exec db psql -U postgres -c "\d open_trades"
```

CHANGELOG:
```
## YYYY-MM-DD — Task 5.1: open_trades table
### Modified
- app/database.py: open_trades table + index
- app/models.py: TradeCreate, TradeResponse models
```

---

## Task 5.2 — Build trades router

READS FIRST:
- app/models.py (TradeCreate, TradeResponse — after Task 5.1)
- app/routers/strategies.py (use as routing pattern)
- app/dependencies.py
- app/services/market_data.py (understand get_or_refresh_data)

GOAL:
Three endpoints. Nothing more.

CREATE: app/routers/trades.py

```python
router = APIRouter(prefix="/trades", tags=["trades"])

@router.post("/", response_model=TradeResponse)
def log_trade(trade: TradeCreate, current_user=Depends(...), db=...):
    # Insert into open_trades for current_user.id
    # Fetch current price via get_or_refresh_data()
    # Compute current_r: (current_price - entry) / (entry - stop)
    # Return TradeResponse

@router.get("/", response_model=list[TradeResponse])
def get_trades(current_user=Depends(...), db=...):
    # Fetch all open trades for current_user where status='open'
    # For each trade: fetch current price, compute current_r
    # Compute exit_alert:
    #   current_price <= stop_loss * 1.02  → "APPROACHING_STOP"
    #   current_price >= target * 0.98     → "AT_TARGET"
    #   else                               → None
    # Return list[TradeResponse]

@router.delete("/{trade_id}")
def close_trade(trade_id: int, current_user=Depends(...), db=...):
    # Verify trade belongs to current_user — 403 if not
    # Update status='closed', exit_price=current_price, exit_date=today
    # Return {"closed": trade_id}
```

MODIFY: app/main.py
  Import and register trades router under JWT auth.

DO NOT add any other endpoints. No PUT/PATCH for editing trades.

VERIFY:
```bash
# Log a test trade
curl -X POST http://localhost:8000/trades/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"SPY","strategy_name":"S1_TrendPullback","strategy_type":"trend",
       "entry_price":660.0,"stop_loss":651.0,"target":670.0,"shares":15}'

# Get open trades
curl http://localhost:8000/trades/ -H "Authorization: Bearer $TOKEN"
```

CHANGELOG:
```
## YYYY-MM-DD — Task 5.2: Trades router
### Added
- app/routers/trades.py: POST /trades, GET /trades, DELETE /trades/{id}
### Modified
- app/main.py: registered trades router
```

---

## Task 5.3 — Add exit monitoring to digest

READS FIRST:
- app/services/digest.py (after phase 4 changes)
- app/routers/trades.py (exit_alert logic from Task 5.2)

GOAL:
The nightly digest checks every user's open trades for exit conditions
and includes alerts in the briefing. One new function only.

ADD to app/services/digest.py:

```python
def generate_trade_alerts(user_id: int) -> str:
    """
    Check all open trades for exit conditions.
    Returns formatted alert string. Empty string if no alerts.
    """
    # 1. Fetch all open trades for user_id where status='open'
    # 2. For each trade: fetch current price
    # 3. Compute current_r and exit_alert (same logic as GET /trades)
    # 4. Format alerts:
    #    "OPEN TRADE ALERTS — [date]\n"
    #    "⚠ [TICKER] [strategy]: approaching stop — current $X.XX stop $X.XX\n"
    #    "✓ [TICKER] [strategy]: at target — current $X.XX target $X.XX\n"
    # 5. Return formatted string. Empty string if no alerts.
```

This function is called by the existing nightly digest alongside
generate_strategy_briefing() from phase 4.

DO NOT change existing digest generation logic.
DO NOT send any notifications in this function — digest.py handles that.

VERIFY:
```python
from app.services.digest import generate_trade_alerts
alerts = generate_trade_alerts(user_id=1)
print(repr(alerts))  # empty string or formatted alerts
print("5.3 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 5.3: Trade exit monitoring in digest
### Modified
- app/services/digest.py: added generate_trade_alerts() function
```

---

## Phase 5 complete checklist

- [ ] open_trades table exists in DB
- [ ] POST /trades logs a trade and returns current_r
- [ ] GET /trades returns open trades with live current_r and exit_alert
- [ ] DELETE /trades/{id} closes a trade
- [ ] generate_trade_alerts() produces formatted alert text
- [ ] `python -m pytest tests/` still passes
- [ ] `python scripts/smoke_test.py` passes
- [ ] Existing routes unchanged
