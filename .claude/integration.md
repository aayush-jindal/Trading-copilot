# Integration — Options Chain Scanner into Trading Copilot

## Goal

Move the Phase A chain scanner from the standalone options repo into
Trading Copilot at `app/services/options/chain_scanner/`, add a DB
table for signal persistence, and expose a `GET /options/chain-scan`
endpoint connected to the existing watchlist.

---

## How imports work in this codebase

**Critical context:** The vendored pricing library at `pricing/src/`
uses bare internal imports (`from models.black_scholes import ...`,
`from .risk_metrics import ...`). These are NOT `app.*` paths.

`pricing/pricer.py` makes this work with a sys.path shim:
```python
_SRC = str(Path(__file__).parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from models.black_scholes import black_scholes_price, calculate_greeks
from monte_carlo.gbm_simulator import run_monte_carlo
```

The chain scanner needs the same pattern — import through the
sys.path shim, using the same bare module names. Do NOT use
`from app.services.options.pricing.src.models...` — that path
does not resolve because `pricing/src/` has no `__init__.py`
at the package level and the internal imports are bare/relative.

---

## Current state

**Options repo** (`options/src/scanner/`) — 11 files, 33 tests:
```
scanner/
├── __init__.py               # OptionSignal dataclass, scan_watchlist()
├── scanner.py                # OptionsScanner orchestrator
├── iv_rank.py                # compute_iv_metrics()
├── contract_filter.py        # filter_contracts()
├── edge.py                   # compute_edge()
├── scorer.py                 # score_signal(), rank_signals()
├── cli.py                    # CLI entry point
└── providers/
    ├── __init__.py            # create_provider() factory
    ├── base.py                # ChainProvider ABC + dataclasses
    ├── yfinance_provider.py   # YFinanceProvider
    └── cached_provider.py     # CachedProvider decorator
```

**Trading Copilot** (`app/services/options/`):
```
options/
├── __init__.py
├── scanner.py              # existing bias-detector scanner (DO NOT TOUCH)
├── bias_detector.py        # frozen
├── config.py               # RISK_FREE_RATE, MC_*, OUTLOOKS, PRICING
├── ai_narrative.py
├── formatter.py
├── opportunity_builder.py
├── strategy_selector.py
└── pricing/
    ├── __init__.py
    ├── pricer.py           # sys.path shim + wrapper functions
    └── src/                # vendored pricing library (FROZEN)
```

**Key patterns to follow:**
- DB: uses `get_db()` → `_Conn` wrapper with `.execute()`, `.commit()`, `.close()`
- Auth: endpoints use `user=Depends(get_current_user)` → returns `{"id": int, "username": str}`
- Router registration: `app.include_router(router, **_auth)` in main.py
- Existing options endpoint: `POST /options/scan` and `GET /options/scan/{ticker}`

---

## Exactly 3 scanner files need import rewiring

The chain scanner imports from the pricing library in 3 files. These
must use the **same sys.path shim pattern** as `pricer.py`.

### 1. `contract_filter.py`

**Current (standalone):**
```python
import sys
import os
...
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from models.black_scholes import calculate_greeks
```

**Replace with:**
```python
from pathlib import Path
import sys

_SRC = str(Path(__file__).resolve().parent.parent / "pricing" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from models.black_scholes import calculate_greeks
```

### 2. `edge.py`

**Current (standalone):**
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from models.black_scholes import black_scholes_price, calculate_greeks
```

**Replace with:**
```python
from pathlib import Path
import sys

_SRC = str(Path(__file__).resolve().parent.parent / "pricing" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from models.black_scholes import black_scholes_price, calculate_greeks
```

### 3. `scanner.py` (the orchestrator, not the existing one)

**Current (standalone):**
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from monte_carlo.garch_vol import fit_garch11
```

**Replace with:**
```python
from pathlib import Path
import sys

_SRC = str(Path(__file__).resolve().parent.parent / "pricing" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from monte_carlo.garch_vol import fit_garch11
```

### Why this works:
`chain_scanner/` lives at `app/services/options/chain_scanner/`.
`parent.parent` from there is `app/services/options/`.
`/ "pricing" / "src"` lands at `app/services/options/pricing/src/`.
This is the same directory `pricer.py` already shims. The bare
imports (`from models.black_scholes`, `from monte_carlo.garch_vol`)
resolve correctly because `pricing/src/` is on sys.path.

### Files that need NO changes:
- `__init__.py`, `iv_rank.py`, `scorer.py` — no pricing imports
- `providers/*` — no pricing imports
- All use relative imports within the scanner package

### `cli.py`:
Replace the sys.path hack with:
```python
from app.services.options.chain_scanner import OptionSignal, scan_watchlist
from app.services.options.chain_scanner.providers import create_provider
```

---

## Task sequence

### Task 1: Copy files + rewire imports

1. Create directories:
```bash
mkdir -p app/services/options/chain_scanner/providers
```

2. Copy all 11 scanner files from the options repo.

3. Rewire the 3 pricing imports as shown above.

4. Rewire cli.py imports.

**Verify:**
```bash
docker exec docker-api-1 python -c "
from app.services.options.chain_scanner import scan_watchlist, OptionSignal
from app.services.options.chain_scanner.providers import create_provider
from app.services.options.chain_scanner.scanner import OptionsScanner
print('All chain_scanner imports OK')
"
```

**Acceptance:** No ModuleNotFoundError.

### Task 2: Add DB table

Add to `app/database.py` `init_db()`, before the final `conn.commit()`:

```python
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_signals (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER REFERENCES users(id),
            ticker              TEXT NOT NULL,
            strike              DOUBLE PRECISION NOT NULL,
            expiry              TEXT NOT NULL,
            option_type         TEXT NOT NULL,
            dte                 INTEGER,
            spot                DOUBLE PRECISION,
            bid                 DOUBLE PRECISION,
            ask                 DOUBLE PRECISION,
            mid                 DOUBLE PRECISION,
            open_interest       INTEGER,
            bid_ask_spread_pct  DOUBLE PRECISION,
            chain_iv            DOUBLE PRECISION,
            iv_rank             DOUBLE PRECISION,
            iv_percentile       DOUBLE PRECISION,
            iv_regime           TEXT,
            garch_vol           DOUBLE PRECISION,
            theo_price          DOUBLE PRECISION,
            edge_pct            DOUBLE PRECISION,
            direction           TEXT,
            delta               DOUBLE PRECISION,
            gamma               DOUBLE PRECISION,
            theta               DOUBLE PRECISION,
            vega                DOUBLE PRECISION,
            conviction          DOUBLE PRECISION,
            scanned_at          TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_option_signals_ticker ON option_signals(ticker)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_option_signals_scanned ON option_signals(scanned_at DESC)"
    )
```

Note: uses `DOUBLE PRECISION` and `TEXT` matching existing table patterns
in database.py (not `FLOAT` or `VARCHAR`).

**Verify:** Restart, then:
```bash
docker exec docker-db-1 psql -U postgres -d trading_copilot -c "\d option_signals"
```

### Task 3: Create API endpoint

Create `app/routers/chain_scan.py`:

```python
"""
Options chain scanner endpoint.

GET /options/chain-scan  — scans watchlist or provided tickers for
                           high-conviction options trade signals.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user
from app.database import get_db
from app.services.options.chain_scanner import scan_watchlist, OptionSignal
from app.services.options.chain_scanner.providers import create_provider
from app.services.options.config import RISK_FREE_RATE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/options", tags=["options"])


@router.get("/chain-scan")
def chain_scan(
    tickers: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    # Resolve tickers
    if tickers:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        db = get_db()
        try:
            rows = db.execute(
                "SELECT ticker FROM watchlist WHERE user_id = %s",
                (user["id"],),
            ).fetchall()
            ticker_list = [r["ticker"] for r in rows]
        finally:
            db.close()

    if not ticker_list:
        return {"signals": [], "total": 0, "tickers_scanned": 0}

    provider = create_provider()
    signals = scan_watchlist(ticker_list, provider=provider)

    _save_signals(signals, user["id"])

    return {
        "signals": [_to_dict(s) for s in signals[:top]],
        "total": len(signals),
        "tickers_scanned": len(ticker_list),
    }


def _to_dict(s: OptionSignal) -> dict:
    return {
        "ticker": s.ticker, "strike": s.strike, "expiry": s.expiry,
        "option_type": s.option_type, "dte": s.dte,
        "spot": s.spot, "bid": s.bid, "ask": s.ask, "mid": s.mid,
        "open_interest": s.open_interest,
        "bid_ask_spread_pct": s.bid_ask_spread_pct,
        "chain_iv": round(s.chain_iv, 4),
        "iv_rank": s.iv_rank, "iv_percentile": s.iv_percentile,
        "iv_regime": s.iv_regime,
        "garch_vol": round(s.garch_vol, 4),
        "theo_price": round(s.theo_price, 4),
        "edge_pct": s.edge_pct, "direction": s.direction,
        "delta": s.delta, "gamma": s.gamma,
        "theta": s.theta, "vega": s.vega,
        "conviction": s.conviction,
    }


def _save_signals(signals: list, user_id: int):
    if not signals:
        return
    db = get_db()
    try:
        for s in signals:
            db.execute("""
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
        db.commit()
    except Exception as e:
        logger.error("Failed to save option signals: %s", e)
    finally:
        db.close()
```

Register in `app/main.py` — add to the imports line:
```python
from app.routers import analysis, auth, data, internal, notifications, options, player, strategies, synthesis, trades, watchlist, chain_scan
```

And add to the protected routes block:
```python
app.include_router(chain_scan.router,    **_auth)
```

**Verify:**
```bash
# Get a token first, then:
curl -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8000/options/chain-scan?tickers=AAPL&top=5"
```

**Acceptance:** Returns JSON with signals. DB has rows in `option_signals`.

### Task 4: Copy and rewire tests

Copy `options/tests/test_scanner.py` → `tests/test_chain_scanner.py`.

Find-replace all imports. The test file uses `sys.path.insert(0, ...)` at
the top — replace with the copilot import paths:

```python
# Remove:
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Replace all scanner imports:
# Old                                          → New
# from scanner.providers.base import ...        → from app.services.options.chain_scanner.providers.base import ...
# from scanner.providers.cached_provider import → from app.services.options.chain_scanner.providers.cached_provider import ...
# from scanner.iv_rank import ...               → from app.services.options.chain_scanner.iv_rank import ...
# from scanner.contract_filter import ...       → from app.services.options.chain_scanner.contract_filter import ...
# from scanner.edge import ...                  → from app.services.options.chain_scanner.edge import ...
# from scanner.scorer import ...                → from app.services.options.chain_scanner.scorer import ...
# from scanner import OptionSignal              → from app.services.options.chain_scanner import OptionSignal
# from scanner.scanner import OptionsScanner    → from app.services.options.chain_scanner.scanner import OptionsScanner
```

**Verify:**
```bash
docker exec docker-api-1 python -m pytest tests/test_chain_scanner.py -v
docker exec docker-api-1 python scripts/smoke_test.py
```

**Acceptance:** 33 scanner tests pass. Smoke test passes.

### Task 5: Config + docs

Add to `app/services/options/config.py` at the bottom:

```python
# ── Chain scanner defaults ─────────────────────────────────────────────
CHAIN_SCANNER_CONFIG = {
    "filter": {
        "min_dte": int(os.getenv("SCANNER_MIN_DTE", "20")),
        "max_dte": int(os.getenv("SCANNER_MAX_DTE", "60")),
        "min_delta": 0.15,
        "max_delta": 0.50,
        "min_open_interest": 100,
        "max_spread_pct": 15.0,
        "moneyness_range": [0.85, 1.15],
    },
    "garch": {
        "history_days": 120,
        "min_returns": 30,
    },
    "scoring_weights": {
        "edge": 0.40,
        "iv_rank": 0.25,
        "liquidity": 0.20,
        "greeks": 0.15,
    },
}
```

Update the endpoint to pass this config:
```python
from app.services.options.config import CHAIN_SCANNER_CONFIG
signals = scan_watchlist(ticker_list, provider=provider, config=CHAIN_SCANNER_CONFIG)
```

Append to CHANGELOG.md.

---

## Files summary

| Action | File |
|--------|------|
| CREATE | `app/services/options/chain_scanner/__init__.py` |
| CREATE | `app/services/options/chain_scanner/scanner.py` |
| CREATE | `app/services/options/chain_scanner/iv_rank.py` |
| CREATE | `app/services/options/chain_scanner/contract_filter.py` |
| CREATE | `app/services/options/chain_scanner/edge.py` |
| CREATE | `app/services/options/chain_scanner/scorer.py` |
| CREATE | `app/services/options/chain_scanner/cli.py` |
| CREATE | `app/services/options/chain_scanner/providers/__init__.py` |
| CREATE | `app/services/options/chain_scanner/providers/base.py` |
| CREATE | `app/services/options/chain_scanner/providers/yfinance_provider.py` |
| CREATE | `app/services/options/chain_scanner/providers/cached_provider.py` |
| CREATE | `app/routers/chain_scan.py` |
| CREATE | `tests/test_chain_scanner.py` |
| MODIFY | `app/database.py` — add option_signals table in init_db() |
| MODIFY | `app/main.py` — register chain_scan router |
| MODIFY | `app/services/options/config.py` — add CHAIN_SCANNER_CONFIG |
| MODIFY | `CHANGELOG.md` |

## Files NOT modified

- `app/services/options/pricing/src/**` — frozen
- `app/services/options/scanner.py` — existing scanner, untouched
- `app/services/options/bias_detector.py` — frozen
- `app/services/options/pricing/pricer.py` — untouched
- `app/routers/options.py` — existing options endpoint, untouched
- `app/routers/synthesis.py` — frozen
- `app/services/ai_engine.py` — frozen
- `app/services/ta_engine.py` — frozen
- `app/services/market_data.py` — frozen
- All existing tests — untouched