# Phase 2 — Strategy factory foundation + backtest all strategies

## Before starting
Phase 1 backtesting framework is complete (data.py, signals.py, base.py,
engine.py, results.py). Read all of them before writing anything here.

## Gate to advance to Phase 3
Every strategy that will appear in the live scanner must pass:
  total_trades >= 30 AND expectancy > 0
on universe defined in Task 2.1, window 2019-01-01 to 2024-01-01.
Record ALL results (pass and fail) in CHANGELOG.md before opening phase3.md.

---

## Task 2.1 — Upgrade base.py: factory dataclasses

READS FIRST:
- backtesting/base.py (current state)
- app/services/ta_engine.py lines 638-899 (swing_setup output shape)

GOAL:
Upgrade base.py with the factory dataclasses that every strategy will use.
These are the shared types. Do not change BacktestEngine or existing logic.

ADD to backtesting/base.py (do not remove anything existing):

1. `Condition` dataclass:
   - label: str          — human readable e.g. "Price above SMA200"
   - passed: bool
   - value: str          — the actual value e.g. "above (+4.2%)"
   - required: str       — what was needed e.g. "above"

2. `RiskLevels` dataclass:
   - entry_price: float
   - stop_loss: float
   - target: float
   - risk_reward: float
   - atr: float | None = None
   - entry_zone_low: float | None = None
   - entry_zone_high: float | None = None
   - position_size: int | None = None   # shares, computed by scanner

3. `StrategyResult` dataclass:
   - name: str
   - type: str           # "trend" | "reversion" | "breakout" | "rotation"
   - verdict: str        # "ENTRY" | "WATCH" | "NO_TRADE"
   - score: int          # 0-100
   - conditions: list[Condition]
   - risk: RiskLevels | None
   - strategy_instance: object | None = None  # for scanner use

4. Upgrade `BaseStrategy` — add to existing ABC:
   - type: str           — class attribute, must be set by subclass
   - evaluate(snapshot: SignalSnapshot) -> StrategyResult  (abstract)
     NOTE: evaluate() replaces the old should_enter/should_exit pattern
     for the scanner use case. Keep should_enter/should_exit for backtest.
   - _check_conditions(snapshot) -> list[Condition]  (abstract)
   - _compute_risk(snapshot) -> RiskLevels | None    (abstract)
   - _verdict(conditions) -> tuple[str, int]
     Default implementation: count passed conditions, map to verdict+score.
     Subclasses may override. Logic:
       all passed    → "ENTRY", score proportional to count
       >=50% passed  → "WATCH", score proportional
       <50% passed   → "NO_TRADE", score proportional

DO NOT MODIFY: engine.py, data.py, signals.py, results.py

VERIFY:
```python
from backtesting.base import Condition, RiskLevels, StrategyResult, BaseStrategy
import inspect
assert inspect.isabstract(BaseStrategy)
assert hasattr(BaseStrategy, 'evaluate')
assert hasattr(BaseStrategy, '_check_conditions')
assert hasattr(BaseStrategy, '_compute_risk')
print("2.1 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.1: Factory dataclasses added to base.py
### Modified
- backtesting/base.py: added Condition, RiskLevels, StrategyResult,
  upgraded BaseStrategy with evaluate(), _check_conditions(), _compute_risk()
### Unchanged
- engine.py, data.py, signals.py, results.py untouched
```

---

## Task 2.2 — Build registry.py

READS FIRST:
- backtesting/base.py (after Task 2.1)
- backtesting/strategies/__init__.py

GOAL:
Create the registry. This is the single place that controls which strategies
are active. Adding a strategy = one line here, nothing else.

CREATE: backtesting/strategies/registry.py

```python
"""
Strategy registry — the only place strategies are registered.

To add a strategy:
  1. Create backtesting/strategies/sN_name.py
  2. Import it here and add one line to STRATEGY_REGISTRY.
  Nothing else changes anywhere.
"""
from .s1_trend_pullback import TrendPullbackStrategy
# future strategies imported here as they are validated

STRATEGY_REGISTRY: list = [
    TrendPullbackStrategy(),
    # new strategies added here after passing backtest gate
]
```

Note: s1_trend_pullback.py already exists from Phase 1. It needs to be
upgraded in Task 2.3 to implement the new evaluate() method. The registry
import will fail until that is done — that is expected.

DO NOT add any other strategies to the registry in this task.

VERIFY:
```python
# Will fail until Task 2.3 — that is expected and correct
# Just confirm the file exists and imports cleanly when s1 is upgraded
import ast, pathlib
src = pathlib.Path("backtesting/strategies/registry.py").read_text()
ast.parse(src)
print("2.2 ok — syntax valid")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.2: Strategy registry created
### Added
- backtesting/strategies/registry.py: STRATEGY_REGISTRY list
```

---

## Task 2.3 — Upgrade S1: add evaluate() to TrendPullbackStrategy

READS FIRST:
- backtesting/strategies/s1_trend_pullback.py (current state)
- backtesting/base.py (after Task 2.1)
- app/services/ta_engine.py lines 638-899 (swing_setup fields)

GOAL:
Add evaluate() to TrendPullbackStrategy using the factory pattern.
Keep should_enter/should_exit/get_stops unchanged — they are used by BacktestEngine.
evaluate() is used by the scanner.

ADD to TrendPullbackStrategy (do not remove anything):

```python
def _check_conditions(self, snapshot) -> list:
    swing = snapshot.swing_setup or {}
    conditions_data = swing.get("conditions", {})
    return [
        Condition(
            label="Uptrend (price above SMA50 & 200)",
            passed=conditions_data.get("uptrend_confirmed", False),
            value="confirmed" if conditions_data.get("uptrend_confirmed") else "not confirmed",
            required="confirmed"
        ),
        Condition(
            label="Weekly trend aligned",
            passed=conditions_data.get("weekly_trend_aligned", False),
            value="bullish" if conditions_data.get("weekly_trend_aligned") else "not bullish",
            required="bullish"
        ),
        Condition(
            label=f"ADX {swing.get('adx', 0):.0f}",
            passed=conditions_data.get("adx_strong", False),
            value=f"{swing.get('adx', 0):.1f}",
            required=">= 20 strong"
        ),
        Condition(
            label="RSI cooled from peak",
            passed=conditions_data.get("rsi_pullback", False),
            value=f"RSI {snapshot.momentum.get('rsi', 0):.1f}",
            required="pullback 40-55"
        ),
        Condition(
            label=f"Near support {snapshot.support_resistance.get('nearest_support', '')}",
            passed=conditions_data.get("near_support", False),
            value=snapshot.support_resistance.get("support_strength", ""),
            required="<= 0.75x ATR"
        ),
        Condition(
            label=f"Volume declining ({snapshot.volume.get('volume_ratio', 0):.2f}x avg)",
            passed=conditions_data.get("volume_declining", False),
            value=f"{snapshot.volume.get('volume_ratio', 0):.2f}x · OBV {snapshot.volume.get('obv_trend','')}",
            required="declining"
        ),
        Condition(
            label="Reversal candle",
            passed=conditions_data.get("reversal_candle", False),
            value="present" if conditions_data.get("reversal_candle") else "none",
            required="bullish pattern"
        ),
        Condition(
            label="Trigger — price breakout",
            passed=conditions_data.get("trigger_fired", False),
            value="fired" if conditions_data.get("trigger_fired") else "waiting",
            required="waiting for breakout"
        ),
    ]

def _compute_risk(self, snapshot) -> object | None:
    swing = snapshot.swing_setup
    if not swing or not swing.get("stop_loss") or not swing.get("target"):
        return None
    entry = snapshot.price
    stop = swing["stop_loss"]
    target = swing["target"]
    risk = entry - stop
    rr = (target - entry) / risk if risk > 0 else 0
    return RiskLevels(
        entry_price=entry,
        stop_loss=stop,
        target=target,
        risk_reward=round(rr, 2),
        atr=swing.get("atr14"),
        entry_zone_low=swing.get("entry_zone", {}).get("low"),
        entry_zone_high=swing.get("entry_zone", {}).get("high"),
    )

def evaluate(self, snapshot) -> object:
    conditions = self._check_conditions(snapshot)
    verdict, score = self._verdict(conditions)
    risk = self._compute_risk(snapshot) if verdict != "NO_TRADE" else None
    return StrategyResult(
        name=self.name,
        type=self.type,
        verdict=verdict,
        score=score,
        conditions=conditions,
        risk=risk,
    )
```

Also add class attribute: `type = "trend"`

VERIFY:
```python
from backtesting.strategies.registry import STRATEGY_REGISTRY
from backtesting.data import YFinanceProvider
from backtesting.signals import SignalEngine
p = YFinanceProvider()
df = p.fetch_daily("SPY", "2024-01-01", "2024-06-01")
snap = SignalEngine().compute(df)
result = STRATEGY_REGISTRY[0].evaluate(snap)
print(result.name, result.verdict, result.score)
print("2.3 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.3: S1 upgraded with evaluate() factory method
### Modified
- backtesting/strategies/s1_trend_pullback.py: added type, evaluate(),
  _check_conditions(), _compute_risk() — should_enter/should_exit unchanged
```

---

## Task 2.4 — Build StrategyScanner

READS FIRST:
- backtesting/strategies/registry.py
- backtesting/base.py (StrategyResult, RiskLevels)
- backtesting/signals.py (SignalEngine)
- app/services/ta_engine.py (understand signal shape)

GOAL:
Build the scanner that runs all registry strategies against live signals
for one ticker and returns a ranked list. This is the core service.

CREATE: backtesting/scanner.py

```python
"""
StrategyScanner — runs all registered strategies against live signals.
Returns results ranked by score descending. NO_TRADE results excluded.

Usage:
    from backtesting.scanner import StrategyScanner
    scanner = StrategyScanner()
    results = scanner.scan("AAPL", account_size=50000, risk_pct=0.01)
"""
```

Class: `StrategyScanner`
- `__init__(self)` — loads STRATEGY_REGISTRY
- `scan(ticker, account_size, risk_pct) -> list[StrategyResult]`
  1. Fetch daily data via YFinanceProvider (last 300 bars)
  2. Compute SignalSnapshot via SignalEngine
  3. Call evaluate(snapshot) on every strategy in registry
  4. Filter out verdict == "NO_TRADE"
  5. For each remaining result, compute position_size:
     `shares = int((account_size * risk_pct) / (entry - stop))`
     only if risk.entry_price and risk.stop_loss are set
     set result.risk.position_size = shares
  6. Sort by score descending
  7. Return list

DO NOT fetch data more than once per scan call.
DO NOT add logging beyond a single print for the ticker being scanned.
DO NOT add any caching in this task — that can be added later if needed.

VERIFY:
```python
from backtesting.scanner import StrategyScanner
scanner = StrategyScanner()
results = scanner.scan("SPY", account_size=50000, risk_pct=0.01)
print(f"SPY: {len(results)} strategies with WATCH/ENTRY verdict")
for r in results:
    print(f"  {r.name}: {r.verdict} score={r.score}")
print("2.4 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.4: StrategyScanner built
### Added
- backtesting/scanner.py: StrategyScanner.scan() — runs registry, ranks results
```

---

## Task 2.5 — Build S2: RSIMeanReversionStrategy

READS FIRST:
- backtesting/base.py (Condition, RiskLevels, StrategyResult, BaseStrategy)
- app/services/ta_engine.py: compute_momentum_signals(), compute_volatility_signals()
- backtesting/strategies/s1_trend_pullback.py (use as exact template)

GOAL:
Build S2 following the factory pattern exactly. Nothing else.

CREATE: backtesting/strategies/s2_rsi_reversion.py

```
Class: RSIMeanReversionStrategy(BaseStrategy)
name  = "S2_RSIMeanReversion"
type  = "reversion"

Conditions (in order, matching UI display):
  1. "Price above SMA200"
     passed: trend["price_vs_sma200"] == "above"
     value:  f"{trend['distance_from_sma200_pct']}%"
     required: "above"

  2. "RSI crossed above 30"
     passed: prev_rsi < 30 AND current rsi >= 30
     value:  f"RSI {rsi:.1f} (was {prev_rsi:.1f})"
     required: "cross above 30"
     NOTE: track prev_rsi per ticker in self._prev_rsi dict

  3. "BB position below 20"
     passed: volatility["bb_position"] < 20
     value:  f"pos {volatility['bb_position']:.0f}%"
     required: "< 20%"

RiskLevels:
  entry_price: snapshot.price
  stop_loss:   snapshot.price - (1.5 * volatility["atr"])
  target:      volatility.get("bb_middle") or snapshot.price + (2 * volatility["atr"])
  risk_reward: (target - entry) / (entry - stop) if stop < entry else 0
  atr:         volatility["atr"]

evaluate(): same pattern as S1 — call _check_conditions, _verdict, _compute_risk

should_enter / should_exit / get_stops: keep for BacktestEngine compatibility
  (these already exist from Phase 1 — do not remove them)
```

After building, ADD to registry.py:
```python
from .s2_rsi_reversion import RSIMeanReversionStrategy
# in STRATEGY_REGISTRY:
RSIMeanReversionStrategy(),
```

VERIFY:
```python
from backtesting.scanner import StrategyScanner
scanner = StrategyScanner()
results = scanner.scan("NVDA", account_size=50000, risk_pct=0.01)
print(f"NVDA: {len(results)} active strategies")
print("2.5 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.5: S2 RSIMeanReversionStrategy
### Added
- backtesting/strategies/s2_rsi_reversion.py
### Modified
- backtesting/strategies/registry.py: S2 registered
```

---

## Task 2.6 — Build S3: BBSqueezeStrategy

READS FIRST:
- backtesting/base.py
- app/services/ta_engine.py: compute_volatility_signals()
  Understand: bb_squeeze, bb_position, bb_upper, bb_lower, bb_width, atr
- backtesting/strategies/s2_rsi_reversion.py (use as template)

CREATE: backtesting/strategies/s3_bb_squeeze.py

```
Class: BBSqueezeStrategy(BaseStrategy)
name  = "S3_BBSqueeze"
type  = "breakout"

Conditions:
  1. "BB squeeze resolved"
     passed: self._prev_squeeze.get(ticker, False) == True AND
             volatility["bb_squeeze"] == False
     value:  "fired" or "not fired"
     required: "squeeze then expand"
     NOTE: track prev_squeeze per ticker in self._prev_squeeze dict

  2. "Price above upper band"
     passed: snapshot.price > volatility["bb_upper"]
     value:  f"${snapshot.price:.2f} vs ${volatility['bb_upper']:.2f}"
     required: "above upper band"

  3. "Volume confirmation"
     passed: volume["volume_ratio"] >= 1.5
     value:  f"{volume['volume_ratio']:.2f}x avg"
     required: ">= 1.5x avg"

  4. "Price above SMA200"
     passed: trend["price_vs_sma200"] == "above"
     value:  trend["price_vs_sma200"]
     required: "above"

RiskLevels:
  entry_price: snapshot.price
  stop_loss:   volatility["bb_lower"]
  target:      snapshot.price + (2 * volatility["atr"])
  risk_reward: computed
  atr:         volatility["atr"]
```

After building, ADD to registry.py.

VERIFY:
```python
from backtesting.scanner import StrategyScanner
scanner = StrategyScanner()
results = scanner.scan("AAPL", account_size=50000, risk_pct=0.01)
names = [r.name for r in results]
print("Active strategies:", names)
print("2.6 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.6: S3 BBSqueezeStrategy
### Added
- backtesting/strategies/s3_bb_squeeze.py
### Modified
- backtesting/strategies/registry.py: S3 registered
```

---

## Task 2.7 — Build S7: MACDCrossStrategy

READS FIRST:
- backtesting/base.py
- app/services/ta_engine.py: compute_momentum_signals()
  Understand: macd, macd_signal, macd_histogram, macd_crossover
- backtesting/strategies/s3_bb_squeeze.py (use as template)

CREATE: backtesting/strategies/s7_macd_cross.py

```
Class: MACDCrossStrategy(BaseStrategy)
name  = "S7_MACDCross"
type  = "trend"

Conditions:
  1. "MACD bullish crossover"
     passed: momentum["macd_crossover"] == "bullish_crossover"
     value:  momentum["macd_crossover"]
     required: "bullish_crossover"

  2. "Price above SMA200"
     passed: trend["price_vs_sma200"] == "above"
     value:  f"{trend.get('distance_from_sma200_pct', 0):.1f}% above"
     required: "above"

  3. "RSI not extended (40-60)"
     passed: 40 <= momentum["rsi"] <= 60
     value:  f"RSI {momentum['rsi']:.1f}"
     required: "40-60 zone"

  4. "Weekly trend bullish"
     passed: weekly.get("weekly_trend") == "BULLISH"
     value:  weekly.get("weekly_trend", "N/A")
     required: "BULLISH"

RiskLevels:
  entry_price: snapshot.price
  stop_loss:   low of current bar — use snapshot.price - volatility["atr"]
               as proxy since we don't have bar low in snapshot
  target:      support_resistance.get("nearest_resistance") or
               snapshot.price + (2 * volatility["atr"])
  risk_reward: computed
  atr:         volatility["atr"]
```

After building, ADD to registry.py.

CHANGELOG:
```
## YYYY-MM-DD — Task 2.7: S7 MACDCrossStrategy
### Added
- backtesting/strategies/s7_macd_cross.py
### Modified
- backtesting/strategies/registry.py: S7 registered
```

---

## Task 2.8 — Build S8, S9, S10 (three simple strategies)

READS FIRST:
- backtesting/base.py
- app/services/ta_engine.py — momentum, trend signals
- backtesting/strategies/s7_macd_cross.py (use as template)

GOAL: Build three strategies in one task. Each follows identical pattern.
Each gets its own file. All three added to registry after all three are built.

---

### S8: StochasticCrossStrategy

CREATE: backtesting/strategies/s8_stochastic_cross.py

```
name = "S8_StochasticCross"
type = "reversion"

Conditions:
  1. "Stochastic K crossed above D from below 20"
     Track prev_k. passed: prev_k < 20 AND stochastic_k >= 20 AND
     stochastic_k > stochastic_d
     value: f"K={stochastic_k:.1f} D={stochastic_d:.1f}"
     required: "cross above 20"

  2. "Price above SMA200"
     passed: trend["price_vs_sma200"] == "above"

  3. "RSI not overbought"
     passed: momentum["rsi"] < 65
     value: f"RSI {momentum['rsi']:.1f}"
     required: "< 65"

RiskLevels:
  entry: snapshot.price
  stop:  support_resistance.get("nearest_support") or price - atr
  target: snapshot.price + (2 * atr) when stochastic > 80
  atr: volatility["atr"]
```

---

### S9: EMACrossStrategy

CREATE: backtesting/strategies/s9_ema_cross.py

```
name = "S9_EMACross"
type = "trend"

Conditions:
  1. "EMA9 crossed above EMA21"
     Track prev_ema9, prev_ema21.
     passed: prev_ema9 <= prev_ema21 AND trend["ema_9"] > trend["ema_21"]
     value: f"EMA9={trend['ema_9']:.2f} EMA21={trend['ema_21']:.2f}"
     required: "EMA9 > EMA21 crossover"

  2. "Price above both EMAs"
     passed: price > trend["ema_9"] AND price > trend["ema_21"]
     value: f"${price:.2f}"
     required: "above EMA9 and EMA21"

  3. "Price above SMA200"
     passed: trend["price_vs_sma200"] == "above"

  4. "Volume not weak"
     passed: volume["volume_ratio"] >= 1.0
     value: f"{volume['volume_ratio']:.2f}x"
     required: ">= 1.0x avg"

RiskLevels:
  entry: snapshot.price
  stop:  trend["ema_21"]   ← EMA21 is the stop
  target: support_resistance.get("nearest_resistance") or price + 2*atr
```

---

### S10: GoldenCrossPullbackStrategy

CREATE: backtesting/strategies/s10_golden_cross_pullback.py

```
name = "S10_GoldenCrossPullback"
type = "trend"

Conditions:
  1. "Golden cross recent (within 10 bars)"
     passed: trend["golden_cross"] == True
     NOTE: golden_cross in ta_engine is True only on the crossover bar.
     Track bars_since_cross. Increment each bar. Reset to 0 when True.
     passed: bars_since_cross <= 10
     value: f"{bars_since_cross} bars ago" or "not recent"
     required: "within 10 bars"

  2. "Price pulled back to SMA50"
     passed: abs(price - trend["sma_50"]) / price < 0.02
     value: f"${price:.2f} vs SMA50 ${trend['sma_50']:.2f}"
     required: "within 2% of SMA50"

  3. "RSI moderate (45-65)"
     passed: 45 <= momentum["rsi"] <= 65
     value: f"RSI {momentum['rsi']:.1f}"
     required: "45-65"

  4. "OBV rising"
     passed: volume["obv_trend"] == "RISING"
     value: volume["obv_trend"]
     required: "RISING"

RiskLevels:
  entry: snapshot.price
  stop:  trend["sma_50"]   ← SMA50 is the stop
  target: support_resistance.get("52w_high") or price + 3*atr
```

After building all three, ADD all three to registry.py in one commit.

VERIFY:
```python
from backtesting.strategies.registry import STRATEGY_REGISTRY
print(f"Registry has {len(STRATEGY_REGISTRY)} strategies")
assert len(STRATEGY_REGISTRY) >= 6
print("2.8 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.8: S8, S9, S10 strategies
### Added
- backtesting/strategies/s8_stochastic_cross.py
- backtesting/strategies/s9_ema_cross.py
- backtesting/strategies/s10_golden_cross_pullback.py
### Modified
- backtesting/strategies/registry.py: S8, S9, S10 registered
```

---

## Task 2.9 — Run full backtest across all strategies (parallelized)

READS FIRST:
- backtesting/run_backtest.py (existing from Phase 1)
- backtesting/results.py (passes_gate conditions)
- backtesting/engine.py (understand what state BacktestEngine holds)

GOAL:
Run all strategies across the full universe in parallel.
Each (strategy, ticker) pair is an independent job — no shared state.
Use Python's concurrent.futures.ProcessPoolExecutor to run them.

Why ProcessPoolExecutor not ThreadPoolExecutor:
  ta_engine and pandas computations are CPU-bound and release the GIL
  inconsistently. Processes avoid GIL contention entirely.
  Each worker gets its own memory space — no shared state bugs.

Why NOT async here:
  yfinance.download() and ta-lib computations are CPU-bound, not I/O-bound.
  asyncio would not help — it only parallelizes waiting, not computing.

Universe:
["SPY","QQQ","AAPL","MSFT","GOOGL","AMZN","NVDA","TSLA","AMD",
 "JPM","BAC","XLF","XLK","XLE","XLV","GLD","IWM","TLT"]

Window: 2019-01-01 to 2024-01-01

MODIFY: backtesting/run_backtest.py

Structure:
```python
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

def _run_one(args: tuple) -> dict:
    """Worker function — runs one strategy on one ticker.
    Must be a top-level function (not a method) for pickling.
    Returns dict with strategy_name, ticker, and TradeLog result.
    """
    strategy_class, ticker, start, end = args
    # Instantiate strategy fresh in each worker — avoids shared state
    strategy = strategy_class()
    engine = BacktestEngine()
    try:
        logs = engine.run(strategy, [ticker], start, end)
        return {"strategy": strategy.name, "ticker": ticker,
                "log": logs[0] if logs else None, "error": None}
    except Exception as e:
        return {"strategy": strategy.name, "ticker": ticker,
                "log": None, "error": str(e)}

if __name__ == "__main__":
    # IMPORTANT: __main__ guard required for ProcessPoolExecutor on macOS/Windows
    from backtesting.strategies.registry import STRATEGY_REGISTRY

    UNIVERSE = [...]
    START, END = "2019-01-01", "2024-01-01"
    MAX_WORKERS = min(multiprocessing.cpu_count(), 8)  # cap at 8

    # Build job list: one per (strategy, ticker) pair
    jobs = [
        (type(s), ticker, START, END)
        for s in STRATEGY_REGISTRY
        for ticker in UNIVERSE
    ]

    all_logs = []
    failed = []

    print(f"Running {len(jobs)} jobs across {MAX_WORKERS} workers...")
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_run_one, job): job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            if result["error"]:
                failed.append(result)
                print(f"  SKIP {result['strategy']} {result['ticker']}: {result['error']}")
            elif result["log"]:
                all_logs.append(result["log"])

    # Analyse results per strategy
    analyzer = ResultsAnalyzer(all_logs)
    analyzer.summary()
    analyzer.to_csv("backtest_results/all_results.csv")

    # Print gate status
    stats = analyzer.compute()
    for s in sorted(stats, key=lambda x: x.strategy_name):
        status = "PASS" if analyzer.passes_gate(s) else "FAIL"
        print(f"{s.strategy_name:30s} {s.total_trades:4d} trades  "
              f"WR={s.win_rate:.1%}  E={s.expectancy:.3f}R  [{status}]")
```

Key rules for the worker function:
- Must be a top-level function (not nested, not a method) — required for pickle
- Must instantiate a fresh strategy and engine — never share instances
- Must catch all exceptions and return them — never crash the pool
- No print statements inside _run_one — they interleave across processes

EXPECTED SPEEDUP:
  Sequential: ~20 tickers × 7 strategies × ~3s each ≈ 7 minutes
  Parallel (8 cores): ≈ 1-2 minutes

CREATE: backtesting/validated_strategies.json
  After running, manually create this file listing strategies that PASSED:
  ```json
  {
    "validated": ["S1_TrendPullback", "S7_MACDCross"],
    "pending": ["S2_RSIMeanReversion", "S3_BBSqueeze"],
    "failed": [],
    "last_run": "YYYY-MM-DD",
    "universe": ["SPY","QQQ",...],
    "window": "2019-01-01 to 2024-01-01"
  }
  ```
  Fill in actual results. This file is read by the scanner in Phase 3.

CREATE: backtesting/validated_strategies.json
  After running, manually create this file listing strategies that PASSED:
  ```json
  {
    "validated": ["S1_TrendPullback", "S7_MACDCross"],
    "pending": ["S2_RSIMeanReversion", "S3_BBSqueeze"],
    "failed": [],
    "last_run": "YYYY-MM-DD",
    "universe": ["SPY","QQQ",...],
    "window": "2019-01-01 to 2024-01-01"
  }
  ```
  Fill in actual results. This file is read by the scanner in Phase 3.

VERIFY:
```bash
python backtesting/run_backtest.py
```
Must complete without errors. Should finish in 1-2 minutes (not 7+).
Results printed for every strategy with PASS/FAIL gate status.

CHANGELOG:
```
## YYYY-MM-DD — Task 2.9: Full backtest run — parallelized
### Modified
- backtesting/run_backtest.py: parallel ProcessPoolExecutor,
  updated universe + all strategies
### Added
- backtesting/validated_strategies.json
### Performance
- Jobs: XX (strategies × tickers)
- Workers: XX cores
- Runtime: XX minutes (vs ~7 min sequential)
### Results — fill in real numbers
- S1:  XX trades WR=XX% E=XX R — PASS/FAIL
- S2:  XX trades WR=XX% E=XX R — PASS/FAIL
- S3:  XX trades WR=XX% E=XX R — PASS/FAIL
- S7:  XX trades WR=XX% E=XX R — PASS/FAIL
- S8:  XX trades WR=XX% E=XX R — PASS/FAIL
- S9:  XX trades WR=XX% E=XX R — PASS/FAIL
- S10: XX trades WR=XX% E=XX R — PASS/FAIL
```

---

## Phase 2 complete checklist

- [ ] base.py has Condition, RiskLevels, StrategyResult, upgraded BaseStrategy
- [ ] registry.py exists with all 7 strategies registered
- [ ] StrategyScanner.scan() runs without errors on any ticker
- [ ] All 7 strategies have evaluate() + _check_conditions() + _compute_risk()
- [ ] run_backtest.py produces results for all strategies
- [ ] validated_strategies.json created with real results filled in
- [ ] CHANGELOG.md has all task entries with real numbers in Task 2.9
- [ ] `python scripts/smoke_test.py` passes
- [ ] `git diff app/` shows zero changes to existing app/ files
- [ ] `python -m pytest tests/` — all original tests passing
