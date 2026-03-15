# Phase 1 — Backtesting framework

## Gate to advance to Phase 2
BacktestEngine must run clean on 5 years of SPY daily data.
All three strategies must show 30+ trades and positive expectancy.
Record results in CHANGELOG.md before opening phase2.md.

---

## Task 1.1 — Package skeleton

READS FIRST:
- app/services/market_data.py
- app/services/ta_engine.py (first 50 lines only)
- app/config.py

GOAL: Create importable package structure. No logic yet.

CREATE:
- backtesting/__init__.py
  ```python
  """
  Backtesting framework for Trading Copilot.
  Wraps ta_engine.py and market_data.py — never modifies them.
  """
  ```
- backtesting/strategies/__init__.py — docstring only
- backtesting/tests/__init__.py — empty
- backtesting/README.md — one paragraph: purpose, read-only relationship
  to ta_engine.py, three planned strategies

VERIFY:
```bash
python -c "import backtesting; print('ok')"
```

CHANGELOG:
```
## YYYY-MM-DD — Task 1.1: backtesting package skeleton
### Added
- backtesting/__init__.py, strategies/__init__.py, tests/__init__.py
- backtesting/README.md
### Unchanged
- All existing app/ files untouched
```

---

## Task 1.2 — data.py

READS FIRST:
- app/services/market_data.py (full file)
- app/services/ta_engine.py (_prepare_dataframe function)

GOAL: DataProvider ABC + YFinanceProvider. Calls yfinance directly
(not get_or_refresh_data — that requires DB).

CREATE: backtesting/data.py

Must contain:
1. `DataProvider` — ABC with:
   - `fetch_daily(ticker, start, end) -> pd.DataFrame`
   - `fetch_weekly(ticker, start, end) -> pd.DataFrame`
   Both return DataFrame: columns [open,high,low,close,volume],
   DatetimeIndex sorted ascending.

2. `YFinanceProvider(DataProvider)`:
   - Uses yf.download(ticker, start=start, end=end, interval="1d")
   - Lowercases column names
   - Drops NaN close rows
   - Raises ValueError if fewer than 100 rows returned

3. `DEFAULT_PROVIDER = YFinanceProvider()`

VERIFY:
```python
from backtesting.data import YFinanceProvider
p = YFinanceProvider()
df = p.fetch_daily("SPY", "2023-01-01", "2024-01-01")
assert len(df) > 200
assert list(df.columns) == ["open","high","low","close","volume"]
print("ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 1.2: DataProvider + YFinanceProvider
### Added
- backtesting/data.py
### Unchanged
- app/services/market_data.py untouched
```

---

## Task 1.3 — signals.py

READS FIRST:
- app/services/ta_engine.py — READ THE ENTIRE FILE before writing
  a single line. Understand every key in every dict returned by:
  compute_trend_signals(), compute_momentum_signals(),
  compute_volatility_signals(), compute_volume_signals(),
  compute_support_resistance(), compute_swing_setup_pullback(),
  analyze_ticker()

GOAL: SignalSnapshot dataclass + SignalEngine that wraps ta_engine.
READ-ONLY. Calls ta_engine functions, never reimplements them.

CREATE: backtesting/signals.py

Must contain:
1. `SignalSnapshot` dataclass:
   - price: float
   - trend: dict
   - momentum: dict
   - volatility: dict
   - volume: dict
   - support_resistance: dict
   - swing_setup: dict | None
   - weekly: dict | None
   - candlestick: list

2. `SignalEngine`:
   - `compute(df, weekly_df=None) -> SignalSnapshot`
   - Calls ta_engine functions directly
   - Never recomputes what ta_engine already computes

VERIFY:
```python
from backtesting.data import YFinanceProvider
from backtesting.signals import SignalEngine
p = YFinanceProvider()
df = p.fetch_daily("SPY", "2022-01-01", "2024-01-01")
snap = SignalEngine().compute(df)
assert snap.price > 0
assert "signal" in snap.trend
assert "rsi" in snap.momentum
print("ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 1.3: SignalEngine + SignalSnapshot
### Added
- backtesting/signals.py
### Unchanged
- app/services/ta_engine.py untouched — called, never modified
```

---

## Task 1.4 — base.py

READS FIRST:
- backtesting/signals.py (SignalSnapshot fields)

GOAL: BaseStrategy ABC + dataclasses every strategy uses.

CREATE: backtesting/base.py

Must contain:
1. `StopConfig` dataclass:
   entry_price, stop_loss, target_1, target_2=None,
   target_3=None, risk_reward=0.0

2. `Trade` dataclass:
   ticker, entry_date, entry_price, stop_loss, target_1,
   exit_date=None, exit_price=None,
   exit_reason=None,  # "target_1"|"stop"|"signal"
   pnl_r=None,        # P&L in R-multiples
   signal_snapshot=None  # dict snapshot at entry

3. `BaseStrategy` (ABC):
   - name: str — class attribute, must be set by every subclass
   - `should_enter(snapshot) -> bool` (abstract)
   - `should_exit(snapshot, trade) -> bool` (abstract)
   - `get_stops(snapshot) -> StopConfig` (abstract)
   - `describe() -> str`

VERIFY:
```python
from backtesting.base import BaseStrategy, Trade, StopConfig
import inspect
assert inspect.isabstract(BaseStrategy)
assert hasattr(BaseStrategy, 'should_enter')
print("ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 1.4: BaseStrategy + dataclasses
### Added
- backtesting/base.py
```

---

## Task 1.5 — engine.py

READS FIRST:
- backtesting/base.py
- backtesting/signals.py
- backtesting/data.py

GOAL: BacktestEngine. Bar-by-bar replay. No look-ahead bias.
Uses df.iloc[:i+1] slice on each bar iteration.

CREATE: backtesting/engine.py

Must contain:
1. `TradeLog` dataclass:
   trades, ticker, strategy_name, start_date, end_date

2. `BacktestEngine`:
   - `__init__(provider=None, min_bars=200)`
     Default: YFinanceProvider()
   - `run(strategy, universe, start, end) -> list[TradeLog]`
   - `_run_ticker(strategy, ticker, df, weekly_df) -> TradeLog`

   Stop logic per bar:
   - close <= stop_loss → exit, reason="stop"
   - close >= target_1 → exit, reason="target_1"
   - else → call strategy.should_exit()
   - pnl_r = (exit - entry) / (entry - stop)

VERIFY:
```python
from backtesting.engine import BacktestEngine
e = BacktestEngine()
print(type(e), "ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 1.5: BacktestEngine
### Added
- backtesting/engine.py
```

---

## Task 1.6 — results.py

READS FIRST:
- backtesting/engine.py (TradeLog, Trade)
- backtesting/base.py (Trade fields)

GOAL: ResultsAnalyzer — stats, summary table, CSV export, gate check.

CREATE: backtesting/results.py

Must contain:
1. `StrategyStats` dataclass:
   strategy_name, ticker, total_trades, win_rate, avg_rr,
   expectancy, max_drawdown_r, profit_factor

2. `ResultsAnalyzer`:
   - `__init__(trade_logs: list[TradeLog])`
   - `compute() -> list[StrategyStats]`
   - `summary()` — prints formatted table to stdout
   - `to_csv(path: str)` — exports all trades
   - `passes_gate(stats) -> bool`
     True if: total_trades >= 30 AND expectancy > 0

VERIFY:
```python
from backtesting.results import ResultsAnalyzer
assert hasattr(ResultsAnalyzer, 'passes_gate')
print("ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 1.6: ResultsAnalyzer
### Added
- backtesting/results.py
```

---

## Task 1.7 — Integration test

READS FIRST:
- All backtesting/ files from Tasks 1.1–1.6

GOAL: Prove full framework wires together using a trivial always-enter
strategy. No real strategy logic needed yet.

CREATE: backtesting/tests/test_framework.py

Write `test_framework_wires_together()`:
- Define `TrivialStrategy(BaseStrategy)` inline:
  should_enter → always True
  should_exit → always False
  get_stops → returns StopConfig with stop 5% below price,
  target 10% above price
- Run BacktestEngine on ["SPY"], 2023-01-01 to 2024-01-01
- Assert: result is list, len > 0, first item has .trades attribute

VERIFY:
```bash
python -m pytest backtesting/tests/test_framework.py -v
```
Must pass.

CHANGELOG:
```
## YYYY-MM-DD — Task 1.7: Framework integration test
### Added
- backtesting/tests/test_framework.py
### Verified
- BacktestEngine runs end-to-end on SPY 2023 daily data
```

---

## Phase 1 complete checklist

Before opening phase2.md confirm all of these:

- [ ] `python -c "import backtesting"` passes
- [ ] `python -m pytest backtesting/tests/` passes
- [ ] `python scripts/smoke_test.py` passes
- [ ] All 7 task CHANGELOG entries written
- [ ] No existing files in app/ were modified
- [ ] `git diff app/` shows zero changes
