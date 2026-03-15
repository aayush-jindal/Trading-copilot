# Phase 3 — Backend API: strategies endpoint + watchlist scanner

## Before starting
Confirm phase2.md complete checklist is fully checked off.
validated_strategies.json must exist with real backtest results.
`git diff app/` must show zero changes.

## Gate to advance to Phase 4
- GET /strategies/SPY returns JSON with ranked strategy results
- GET /scan/watchlist returns results for all watchlist tickers
- Both endpoints are JWT protected and user-specific
- `python -m pytest tests/` still passes

---

## Task 3.1 — Update StrategyScanner to respect validated_strategies.json

READS FIRST:
- backtesting/scanner.py (current state)
- backtesting/validated_strategies.json (results from phase 2)
- backtesting/strategies/registry.py

GOAL:
The scanner should only run strategies that appear in the "validated" list
in validated_strategies.json. Strategies in "pending" or "failed" are
loaded but not run.

MODIFY: backtesting/scanner.py

Add to __init__:
  Load validated_strategies.json.
  Filter STRATEGY_REGISTRY to only instances whose name is in
  validated_strategies["validated"].
  Store as self._active_strategies.

scan() uses self._active_strategies, not the full registry.

IMPORTANT — thread safety (required for Task 3.4 parallel watchlist scan):
scan() will be called from multiple threads simultaneously. Ensure:
  - self._active_strategies is set once in __init__, never mutated after
  - scan() has no mutable instance state — each call fully self-contained
  - YFinanceProvider fetches are per-call, not cached on the instance

This means: adding a strategy to the live scanner = passing the backtest gate
AND adding it to validated_strategies.json. No code changes needed.

DO NOT modify registry.py.

VERIFY:
```python
from backtesting.scanner import StrategyScanner
s = StrategyScanner()
print(f"Active strategies: {[str(x.name) for x in s._active_strategies]}")
# Should only show strategies in validated_strategies.json "validated" list
print("3.1 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 3.1: Scanner filters to validated strategies only
### Modified
- backtesting/scanner.py: loads validated_strategies.json, filters registry
```

---

## Task 3.2 — Add user settings to DB schema

READS FIRST:
- app/database.py (full file — understand schema init pattern)
- app/models.py (existing Pydantic models)

GOAL:
Users need account_size and risk_pct stored so the scanner can compute
position sizing. Add these two fields to the users table.
Default: account_size=10000, risk_pct=0.01 (1%).

MODIFY: app/database.py
  In the schema init SQL, add to users table:
  ```sql
  account_size  NUMERIC(12,2) DEFAULT 10000.00,
  risk_pct      NUMERIC(5,4)  DEFAULT 0.0100
  ```
  Use ALTER TABLE IF NOT EXISTS pattern so it is safe to run on
  existing databases.

MODIFY: app/models.py
  Add UserSettings Pydantic model:
  ```python
  class UserSettings(BaseModel):
      account_size: float = 10000.0
      risk_pct: float = 0.01
  ```

DO NOT add a new router in this task. Settings endpoint comes in Task 3.3.

VERIFY:
```bash
docker compose exec db psql -U postgres -c \
  "\d users"
```
account_size and risk_pct columns must appear.

CHANGELOG:
```
## YYYY-MM-DD — Task 3.2: User settings columns added to DB
### Modified
- app/database.py: account_size + risk_pct columns on users table
- app/models.py: UserSettings model added
```

---

## Task 3.3 — Build /strategies/{ticker} endpoint

READS FIRST:
- app/routers/analysis.py (use as routing pattern)
- app/dependencies.py (get_current_user dependency)
- app/main.py (router registration pattern)
- backtesting/scanner.py (StrategyScanner.scan signature)
- app/models.py (UserSettings)

GOAL:
New router that runs StrategyScanner for one ticker using the requesting
user's account_size and risk_pct. Returns ranked strategy results as JSON.

CREATE: app/routers/strategies.py

```python
router = APIRouter(prefix="/strategies", tags=["strategies"])

@router.get("/{ticker}")
def get_strategies(
    ticker: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    # 1. Fetch user's account_size and risk_pct from DB
    # 2. Validate ticker exists via get_or_refresh_data()
    #    → 404 if not found
    # 3. Run StrategyScanner(ticker, account_size, risk_pct)
    #    → 503 if scanner fails (wrap in try/except)
    # 4. Return list of StrategyResult as dicts
    #    → Convert dataclasses to dicts for JSON serialisation
```

Response shape (one item per active strategy with WATCH/ENTRY verdict):
```json
[
  {
    "name": "S1_TrendPullback",
    "type": "trend",
    "verdict": "ENTRY",
    "score": 82,
    "conditions": [
      {"label": "Uptrend", "passed": true, "value": "confirmed", "required": "confirmed"},
      ...
    ],
    "risk": {
      "entry_price": 662.10,
      "stop_loss": 651.30,
      "target": 669.77,
      "risk_reward": 0.68,
      "atr": 9.53,
      "position_size": 45
    }
  }
]
```

MODIFY: app/main.py
  Import strategies router. Register under JWT auth middleware.
  Same pattern as analysis router.

DO NOT modify any existing router.

VERIFY:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=changeme" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl http://localhost:8000/strategies/SPY \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```
Must return JSON array. Each item must have name, type, verdict, score,
conditions array, risk object.

CHANGELOG:
```
## YYYY-MM-DD — Task 3.3: GET /strategies/{ticker} endpoint
### Added
- app/routers/strategies.py
### Modified
- app/main.py: registered strategies router
```

---

## Task 3.4 — Build /scan/watchlist endpoint

READS FIRST:
- app/routers/watchlist.py (understand how watchlist is fetched per user)
- app/routers/strategies.py (after Task 3.3 — reuse scanner call pattern)
- app/dependencies.py
- backtesting/scanner.py (StrategyScanner.scan signature)

GOAL:
New endpoint that runs the strategy scanner across every ticker in the
requesting user's watchlist IN PARALLEL. Returns all results sorted by
highest score across all tickers and strategies.

Why parallel here:
  Each ticker scan is independent — fetch data, compute signals, evaluate.
  With 40 tickers at ~2s each that's 80s sequential, ~5s parallel.
  The morning briefing becomes instant instead of slow.

Why ThreadPoolExecutor not ProcessPoolExecutor here:
  This is a FastAPI endpoint — we're in an async web server.
  The bottleneck is yfinance HTTP requests (I/O-bound), not CPU.
  Threads are correct for I/O-bound work inside a web server.
  Processes would fork the entire FastAPI app — wrong tool here.

ADD to app/routers/strategies.py (same file, new endpoint):

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

@router.get("/scan/watchlist")
def scan_watchlist(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    # 1. Fetch user's watchlist tickers from DB
    tickers = _get_user_watchlist(current_user.id, db)
    if not tickers:
        return []

    # 2. Fetch user's account_size and risk_pct
    account_size, risk_pct = _get_user_settings(current_user.id, db)

    # 3. Scan all tickers in parallel
    scanner = StrategyScanner()
    all_results = []
    MAX_WORKERS = min(len(tickers), 10)  # cap at 10 threads

    def _scan_one(ticker: str) -> list:
        """Scan one ticker. Returns list of results with ticker field added."""
        try:
            results = scanner.scan(ticker, account_size, risk_pct)
            for r in results:
                r.ticker = ticker  # attach ticker to each result
            return results
        except Exception as e:
            print(f"Scanner skip {ticker}: {e}")
            return []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_scan_one, t): t for t in tickers}
        for future in as_completed(futures):
            all_results.extend(future.result())

    # 4. Sort by score descending across all tickers and strategies
    all_results.sort(key=lambda r: r.score, reverse=True)

    # 5. Convert to JSON-serialisable dicts and return
    return [_result_to_dict(r) for r in all_results]
```

Key rules for _scan_one:
- Must catch all exceptions — a bad ticker must never crash the pool
- StrategyScanner instance is shared across threads — it must be stateless
  (verify scanner.scan() has no mutable instance state before shipping)
- Only WATCH/ENTRY results returned — NO_TRADE already filtered by scanner

DO NOT add a new router file. This endpoint belongs in strategies.py.
DO NOT change the watchlist router.
DO NOT use ProcessPoolExecutor — threads are correct inside FastAPI.

VERIFY:
```bash
# Time the request to confirm parallelization is working
time curl http://localhost:8000/strategies/scan/watchlist \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```
Must return ranked list. Empty array valid if watchlist empty.
With 5+ watchlist tickers should complete in under 10 seconds.
Sequential would take 10-15s+ — if slow, parallelization is not working.

CHANGELOG:
```
## YYYY-MM-DD — Task 3.4: GET /strategies/scan/watchlist — parallel
### Modified
- app/routers/strategies.py: /scan/watchlist with ThreadPoolExecutor
### Performance
- Threads: min(tickers, 10)
- Expected: ~5s for 40 tickers vs ~80s sequential
```

---

## Task 3.5 — Add user settings endpoint

READS FIRST:
- app/routers/auth.py (understand current user endpoint patterns)
- app/models.py (UserSettings)
- app/database.py (how user records are queried)

GOAL:
Users need to be able to set their account_size and risk_pct.
One GET to read, one PATCH to update.

ADD to app/routers/strategies.py:

```python
@router.get("/settings")
def get_settings(current_user = Depends(get_current_user), db = ...):
    # Return user's account_size and risk_pct

@router.patch("/settings")
def update_settings(
    settings: UserSettings,
    current_user = Depends(get_current_user),
    db = ...
):
    # Validate: account_size > 0, 0 < risk_pct <= 0.05 (max 5% risk)
    # Update DB
    # Return updated settings
```

Validation rules (enforced in code, not just docs):
- account_size must be > 0
- risk_pct must be > 0 and <= 0.05

DO NOT add a separate router file.

VERIFY:
```bash
curl -X PATCH http://localhost:8000/strategies/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_size": 50000, "risk_pct": 0.01}'

curl http://localhost:8000/strategies/settings \
  -H "Authorization: Bearer $TOKEN"
```
Second call must return the updated values.

CHANGELOG:
```
## YYYY-MM-DD — Task 3.5: User settings endpoints
### Modified
- app/routers/strategies.py: GET /strategies/settings, PATCH /strategies/settings
```

---

## Phase 3 complete checklist

- [ ] StrategyScanner only runs validated strategies
- [ ] GET /strategies/{ticker} returns ranked JSON
- [ ] GET /strategies/scan/watchlist returns ranked JSON across watchlist
- [ ] GET/PATCH /strategies/settings reads and updates user account settings
- [ ] Position sizing uses user's actual account_size and risk_pct
- [ ] All endpoints are JWT protected
- [ ] `python -m pytest tests/` still passes
- [ ] `python scripts/smoke_test.py` passes
- [ ] Existing routes untouched
