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

## Task 2.9 — Run full backtest: expanded universe + train/test split (parallelized)

READS FIRST:
- backtesting/run_backtest.py (existing from Phase 1)
- backtesting/results.py (passes_gate conditions)
- backtesting/engine.py (understand what state BacktestEngine holds)

GOAL:
Run all strategies across the expanded 40-ticker universe using a proper
80/20 train/test split. Parallel execution via ProcessPoolExecutor.
Two-stage gate: strategy must pass on BOTH train and test to be validated.

---

### Universe — 40 tickers across 7 categories

```python
UNIVERSE = [
    # Broad market ETFs
    "SPY", "QQQ", "IWM", "DIA", "EEM", "EFA",
    # Sector ETFs (all 1998+)
    "XLF", "XLK", "XLE", "XLV", "XLY", "XLI", "XLB", "XLP",
    # Large-cap tech (includes TSLA — starts from 2010 naturally)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "AMD", "TSLA", "META", "NFLX",
    # Large-cap blue chips (S10 golden cross candidates)
    "JPM", "BAC", "XOM", "V", "MA", "UNH", "HD",
    # Mid-cap volatile growth (S2 RSI fix)
    "CRM", "SQ", "SHOP", "BRK-B",
    # Commodities
    "GLD", "SLV", "USO", "TLT",
    # Real estate
    "VNQ", "XLRE",
]
```

Why each category exists — see ARCHITECTURE_DECISIONS.md ADR-014.

---

### Train/test split

```python
TRAIN_START = "2005-01-01"
TRAIN_END   = "2021-01-01"   # 16 years — 80%
TEST_START  = "2021-01-01"
TEST_END    = "2026-01-01"   # 5 years  — 20%
```

Per-ticker window rule:
  Each ticker uses max(TRAIN_START, ticker_first_available_date).
  TSLA available 2010-06-29 → train starts 2010-06-29, not 2005.
  SHOP available 2015-09-25 → train starts 2015-09-25.
  Shorter history = fewer bars contributed, not excluded.

Two-stage gate:
  TRAIN gate: total_trades >= 30 AND expectancy > 0
  TEST gate:  total_trades >= 20 AND expectancy > 0
  BOTH must pass → "validated"
  Train passes, test fails → "pending" (likely regime-sensitive)
  Train fails → classify as Level 1/2/3 per tuning plan

---

### Code structure

```python
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Per-ticker start dates — use max(TRAIN_START, ticker_ipo)
TICKER_STARTS = {
    "TSLA":  "2010-06-29",
    "META":  "2012-05-18",
    "V":     "2008-03-19",
    "SQ":    "2015-11-19",
    "SHOP":  "2015-05-21",
    "XLRE":  "2015-10-08",
    # all others default to TRAIN_START = "2005-01-01"
}

def _get_start(ticker: str, phase: str) -> str:
    """Return correct start date for this ticker and phase."""
    if phase == "train":
        default = TRAIN_START
        return max(TICKER_STARTS.get(ticker, default), default)
    else:
        return TEST_START

def _run_one(args: tuple) -> dict:
    """Worker — runs one strategy on one ticker for one phase.
    Top-level function required for pickle compatibility.
    """
    strategy_class, ticker, start, end, phase = args
    strategy = strategy_class()
    engine = BacktestEngine()
    try:
        logs = engine.run(strategy, [ticker], start, end)
        return {
            "strategy": strategy.name, "ticker": ticker,
            "phase": phase, "log": logs[0] if logs else None,
            "error": None
        }
    except Exception as e:
        return {
            "strategy": strategy.name, "ticker": ticker,
            "phase": phase, "log": None, "error": str(e)
        }

if __name__ == "__main__":
    from backtesting.strategies.registry import STRATEGY_REGISTRY

    MAX_WORKERS = min(multiprocessing.cpu_count(), 8)

    # Build jobs for both phases
    jobs = []
    for s in STRATEGY_REGISTRY:
        for ticker in UNIVERSE:
            # TRAIN job
            start = _get_start(ticker, "train")
            jobs.append((type(s), ticker, start, TRAIN_END, "train"))
            # TEST job
            jobs.append((type(s), ticker, TEST_START, TEST_END, "test"))

    train_logs, test_logs = [], []
    print(f"Running {len(jobs)} jobs ({MAX_WORKERS} workers)...")

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_run_one, job): job for job in jobs}
        for future in as_completed(futures):
            r = future.result()
            if r["error"]:
                print(f"  SKIP {r['strategy']} {r['ticker']} [{r['phase']}]: {r['error']}")
            elif r["log"]:
                if r["phase"] == "train":
                    train_logs.append(r["log"])
                else:
                    test_logs.append(r["log"])

    # Analyse each phase separately
    train_analyzer = ResultsAnalyzer(train_logs)
    test_analyzer  = ResultsAnalyzer(test_logs)

    train_stats = {s.strategy_name: s for s in train_analyzer.compute()}
    test_stats  = {s.strategy_name: s for s in test_analyzer.compute()}

    # Two-stage gate
    print("\n=== RESULTS ===")
    print(f"{'Strategy':30s} {'TRAIN':30s} {'TEST':25s} {'VERDICT':10s}")
    print("-" * 100)

    TRAIN_GATE = lambda s: s.total_trades >= 30 and s.expectancy > 0
    TEST_GATE  = lambda s: s.total_trades >= 20 and s.expectancy > 0

    for name in sorted(train_stats.keys()):
        tr = train_stats[name]
        te = test_stats.get(name)
        train_pass = TRAIN_GATE(tr)
        test_pass  = TEST_GATE(te) if te else False

        if train_pass and test_pass:
            verdict = "VALIDATED"
        elif train_pass and not test_pass:
            verdict = "PENDING"   # passes train, fails test
        else:
            verdict = "FAILED"

        tr_str = f"{tr.total_trades}t WR={tr.win_rate:.1%} E={tr.expectancy:.3f}R"
        te_str = f"{te.total_trades}t WR={te.win_rate:.1%} E={te.expectancy:.3f}R" if te else "no data"
        print(f"{name:30s} {tr_str:30s} {te_str:25s} [{verdict}]")

    # Export CSVs
    train_analyzer.to_csv("backtest_results/train_results.csv")
    test_analyzer.to_csv("backtest_results/test_results.csv")
```

Key rules for worker function:
- Top-level function — required for pickle (not method, not lambda)
- Fresh strategy + engine per call — never share instances across workers
- Catches all exceptions — never crash the pool
- No print inside _run_one — output interleaves across processes

EXPECTED SPEEDUP:
  Jobs: 40 tickers × 7 strategies × 2 phases = 560 jobs
  Sequential: ~560 × 2s ≈ 18 minutes
  Parallel (8 cores): ≈ 3-4 minutes

---

### After running: classify and tune

Read the output and classify each non-validated strategy:

LEVEL 1 — too few trades (wrong universe):
  Fix: expand universe further. Do NOT change strategy logic.
  Re-run backtest with added tickers. Max 2 expansion attempts.

LEVEL 2 — reasonable trades, near-zero or negative expectancy:
  Means right signal, wrong threshold. ONE parameter change at a time.
  Tuning plan per strategy:

  S2 RSIMeanReversion (if still failing after expansion):
    Iter 1: tighten stop from 1.5×ATR to 1.0×ATR
    Iter 2: add volume_ratio > 1.2x on entry bar
    Iter 3: stricter RSI — require RSI < 35 two bars ago before cross
    After 3 iters with no pass: retire

  S3 BBSqueeze (if expectancy near zero):
    Iter 1: replace bb_upper exit with ATR trailing stop
    Iter 2: tighten volume entry from 1.5× to 2.0×
    After 2 iters with no pass: accept as-is (already passed original gate)

  S10 GoldenCrossPullback (if train passes, test fails):
    Iter 1: tighten "within 10 bars" to "within 5 bars"
    Iter 2: add weekly trend confirmation (weekly SMA10 > SMA40)
    After 2 iters with no pass: pending — monitor in paper trading

LEVEL 3 — large negative expectancy, high trade count:
  Retire immediately. Do not tune.

HARD RULES FOR ALL TUNING:
  - Never tune on the test set
  - One parameter change per iteration
  - Maximum 3 iterations per strategy
  - Each iteration requires full train re-run, not spot check
  - A strategy passes only when BOTH train AND test pass their gates
  - Train passes, test fails = curve fitted = retire or pending

---

CREATE: backtesting/validated_strategies.json

Fill in after running. Structure now includes train/test results:
```json
{
  "validated": [],
  "pending": [],
  "retired": [],
  "last_run": "YYYY-MM-DD",
  "universe": ["SPY","QQQ","IWM",...],
  "train_window": "per-ticker max(2005-01-01, ipo) to 2021-01-01",
  "test_window": "2021-01-01 to 2026-01-01",
  "results": {
    "S1_TrendPullback": {
      "train": {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "gate": "PASS"},
      "test":  {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "gate": "PASS"},
      "verdict": "VALIDATED"
    }
  },
  "tuning_log": []
}
```

The "tuning_log" array records every parameter change attempted:
```json
{
  "tuning_log": [
    {
      "strategy": "S2_RSIMeanReversion",
      "iteration": 1,
      "change": "stop from 1.5xATR to 1.0xATR",
      "train_result": {"trades": 0, "expectancy": 0.0, "gate": "PASS"},
      "test_result":  {"trades": 0, "expectancy": 0.0, "gate": "FAIL"},
      "outcome": "retired — curve fitted"
    }
  ]
}
```

This file is the complete audit trail. Never delete entries.

VERIFY:
```bash
python backtesting/run_backtest.py
```
Must complete in 3-4 minutes. Prints two-stage gate results for all strategies.

CHANGELOG:
```
## YYYY-MM-DD — Task 2.9: Expanded backtest — 40 tickers, train/test split
### Modified
- backtesting/run_backtest.py: 40-ticker universe, 80/20 train/test split,
  two-stage gate, tuning classification, ProcessPoolExecutor
### Added
- backtesting/validated_strategies.json: full results + tuning_log
### Universe
- 40 tickers across 7 categories (see ARCHITECTURE_DECISIONS.md ADR-014)
- Per-ticker start: max(2005-01-01, ticker_ipo)
### Train window: per-ticker start to 2021-01-01
### Test window:  2021-01-01 to 2026-01-01
### Performance
- Jobs: 560 (40 tickers × 7 strategies × 2 phases)
- Workers: XX cores
- Runtime: XX minutes
### Results — fill in after running
Train / Test / Verdict:
- S1:  XXXt WR=XX% E=XX / XXt WR=XX% E=XX — VALIDATED/PENDING/FAILED
- S2:  XXXt WR=XX% E=XX / XXt WR=XX% E=XX — VALIDATED/PENDING/FAILED
- S3:  XXXt WR=XX% E=XX / XXt WR=XX% E=XX — VALIDATED/PENDING/FAILED
- S7:  XXXt WR=XX% E=XX / XXt WR=XX% E=XX — VALIDATED/PENDING/FAILED
- S8:  XXXt WR=XX% E=XX / XXt WR=XX% E=XX — VALIDATED/PENDING/FAILED
- S9:  XXXt WR=XX% E=XX / XXt WR=XX% E=XX — VALIDATED/PENDING/FAILED
- S10: XXXt WR=XX% E=XX / XXt WR=XX% E=XX — VALIDATED/PENDING/FAILED
### Tuning applied
- [fill in any tuning iterations with parameter changes and outcomes]
```

---

## Task 2.10 — S8 enhanced variant: add SMA200 trend filter

## Context — read before starting

S8 StochasticCross validated with: train WR=57.1% E=+0.166R (3602t),
test WR=54.2% E=+0.133R (1000t). Real edge, but 200 signals/year on the
39-ticker universe (~5/wk on a personal watchlist) is high volume for
thin-per-trade edge (avg_win ~1.07R, avg_loss ~1.0R).

The hypothesis: stochastic crosses above 20 in stocks trading ABOVE their
SMA200 (oversold in an uptrend) are higher quality than crosses in stocks
below SMA200 (dead cat bounces in downtrends). Adding price > SMA200 as a
required condition should reduce volume and improve per-trade expectancy.

This task tests that hypothesis as a parallel candidate, not a replacement.
S8 stays in the registry and scanner unless S8v2 strictly dominates.

READS FIRST:
- backtesting/strategies/s8_stochastic_cross.py (full file)
- backtesting/base.py (_stop_is_valid, _verdict, BaseStrategy)
- backtesting/data.py (SQLiteProvider — use this, not YFinanceProvider)
- backtesting/validated_strategies.json (current S8 baseline numbers)

---

### Step 1 — Create S8v2 strategy file

CREATE: backtesting/strategies/s8v2_stochastic_sma_filter.py

Copy s8_stochastic_cross.py exactly. Then make ONE change only:

Add as the first condition in _check_conditions():
```python
Condition(
    label="Uptrend filter (price above SMA200)",
    passed=trend.get("price_vs_sma200") == "above",
    value="above" if trend.get("price_vs_sma200") == "above" else "below",
    required="above"
)
```

Everything else — entry logic, stop logic, exit logic, all other conditions,
_compute_risk(), _stop_is_valid() call — identical to S8.

Class name: StochasticSmaTrendStrategy
name = "S8v2_StochasticSmaTrend"
type = "reversion"

DO NOT modify s8_stochastic_cross.py.
DO NOT register S8v2 in registry.py yet — that happens only after it passes.

---

### Step 2 — Run comparison backtest from local DB

READS FIRST:
- backtesting/run_backtest.py (current structure)
- backtesting/data.py (SQLiteProvider)

The local SQLite DB already has all 39 tickers cached. Use it.

CREATE: backtesting/run_s8_comparison.py

This is a standalone script — it does NOT use run_backtest.py.
It runs only S8 and S8v2, reads from SQLiteProvider, prints comparison.

```python
"""
S8 vs S8v2 comparison backtest.
Reads from local SQLite DB — no yfinance calls.
Usage: python backtesting/run_s8_comparison.py
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing, json
from backtesting.data import SQLiteProvider
from backtesting.engine import BacktestEngine
from backtesting.results import ResultsAnalyzer
from backtesting.strategies.s8_stochastic_cross import StochasticCrossStrategy
from backtesting.strategies.s8v2_stochastic_sma_filter import StochasticSmaTrendStrategy

UNIVERSE = [...]   # same 39 tickers as run_backtest.py — copy exactly
TICKER_STARTS = {...}  # same per-ticker start dates — copy exactly
TRAIN_END  = "2021-01-01"
TEST_START = "2021-01-01"
TEST_END   = "2026-01-01"

STRATEGIES = [StochasticCrossStrategy, StochasticSmaTrendStrategy]

def _run_one(args):
    strategy_class, ticker, start, end, phase = args
    strategy = strategy_class()
    engine = BacktestEngine(data_provider=SQLiteProvider())
    try:
        logs = engine.run(strategy, [ticker], start, end)
        return {"strategy": strategy.name, "ticker": ticker,
                "phase": phase, "log": logs[0] if logs else None, "error": None}
    except Exception as e:
        return {"strategy": strategy.name, "ticker": ticker,
                "phase": phase, "log": None, "error": str(e)}

if __name__ == "__main__":
    jobs = []
    for cls in STRATEGIES:
        for ticker in UNIVERSE:
            start = TICKER_STARTS.get(ticker, "2005-01-01")
            jobs.append((cls, ticker, start, TRAIN_END, "train"))
            jobs.append((cls, ticker, TEST_START, TEST_END, "test"))

    MAX_WORKERS = min(multiprocessing.cpu_count(), 8)
    train_logs, test_logs = [], []

    print(f"Running {len(jobs)} jobs ({MAX_WORKERS} workers, reading from SQLite)...")
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_run_one, j): j for j in jobs}
        for f in as_completed(futures):
            r = f.result()
            if r["error"]:
                print(f"  SKIP {r['strategy']} {r['ticker']}: {r['error']}")
            elif r["log"]:
                (train_logs if r["phase"] == "train" else test_logs).append(r["log"])

    # Print side-by-side comparison
    train_stats = {s.strategy_name: s for s in ResultsAnalyzer(train_logs).compute()}
    test_stats  = {s.strategy_name: s for s in ResultsAnalyzer(test_logs).compute()}

    print()
    print(f"{'Strategy':35s}  {'TRAIN':35s}  {'TEST':35s}  VERDICT")
    print("-" * 120)

    TRAIN_GATE = lambda s: s.total_trades >= 30 and s.expectancy > 0
    TEST_GATE  = lambda s: s.total_trades >= 20 and s.expectancy > 0

    for name in sorted(train_stats):
        tr = train_stats[name]
        te = test_stats.get(name)
        tp = TRAIN_GATE(tr)
        xp = TEST_GATE(te) if te else False
        verdict = "PASS" if tp and xp else ("TRAIN_ONLY" if tp else "FAIL")
        tr_s = f"{tr.total_trades:4d}t WR={tr.win_rate:.1%} E={tr.expectancy:+.4f}R"
        te_s = f"{te.total_trades:4d}t WR={te.win_rate:.1%} E={te.expectancy:+.4f}R" if te else "—"
        print(f"{name:35s}  {tr_s:35s}  {te_s:35s}  [{verdict}]")
```

VERIFY: Script completes in under 2 minutes (SQLite reads, no network).
Results print for both strategies side-by-side.

---

### Step 3 — Decision rules

Read the output and apply exactly one of these outcomes:

**S8v2 PASSES both gates AND improves on S8:**
  Criteria: test E(v2) > E(S8) AND test WR(v2) >= WR(S8) - 3pp
  Action:
  1. Register S8v2 in registry.py INSTEAD OF S8
     (replace S8 import and instance — one line change)
  2. Update validated_strategies.json:
     - Move S8 to "superseded" key (new key, not retired, not validated)
     - Add S8v2 to "validated"
     - Add tuning_log entry documenting the comparison
  3. Remove S8 from registry — it is superseded, not retired

**S8v2 PASSES both gates but does NOT improve on S8:**
  Criteria: both pass gates but v2 E is similar or lower
  Action:
  1. Keep S8 in registry as-is
  2. Note S8v2 result in tuning_log — filter did not improve quality
  3. Do not register S8v2
  4. If results are IDENTICAL (same trades, same WR, same E to 3dp):
     This means S8's should_enter() already implements the filter.
     Document which condition in should_enter() is responsible.
     Add that condition explicitly to _check_conditions() so the
     scanner interface matches the backtest interface — see Step 5.

**S8v2 FAILS either gate:**
  Action:
  1. Keep S8 in registry as-is
  2. Note S8v2 result in tuning_log — filter reduced signal count too much
  3. Do not register S8v2

DO NOT run a second tuning iteration on S8v2 regardless of outcome.
This is one attempt. S8 is validated. If v2 doesn't improve it, move on.

---

### Step 5 — Backtest/scanner consistency check (run if results are identical)

If S8 and S8v2 produced identical results, it means S8's `should_enter()`
already implements the SMA200 filter. This creates a silent inconsistency:

  - `should_enter()` enforces SMA200 → backtest only validated SMA200-filtered trades
  - `_check_conditions()` may not include SMA200 → scanner can fire on non-SMA200 stocks
  - Result: scanner fires signals that the backtest never tested

This is the most dangerous class of bug — the system appears to work but
the live scanner is operating outside the validated envelope.

FIX: Read s8_stochastic_cross.py. Find every condition in `should_enter()`
that is not already represented in `_check_conditions()`. Add each missing
condition as a Condition object. Do not change the logic — make it visible.

After the fix, `_check_conditions()` must be a complete superset of every
filter applied in `should_enter()`. The rule: if `should_enter()` checks it,
`_check_conditions()` must show it.

Check all other strategies for the same issue while here — any condition in
`should_enter()` that is absent from `_check_conditions()` is a hidden filter.

VERIFY:
```python
# Manual review — read should_enter() and _check_conditions() for each strategy
# Confirm every should_enter() condition has a matching Condition in _check_conditions()
# Document any gaps found in CHANGELOG.md
```

CHANGELOG addition:
```
### Consistency fix
- s8_stochastic_cross.py: SMA200 condition added to _check_conditions() —
  was already enforced in should_enter() but invisible to scanner
- [list any other strategies fixed]
- Root cause: should_enter() and _check_conditions() written independently,
  no enforcement that they stay in sync. Fixed by convention: _check_conditions()
  must be a superset of should_enter() filters.
```

---

### Step 4 — Update validated_strategies.json

Add tuning_log entry regardless of outcome:
```json
{
  "strategy": "S8_StochasticCross",
  "iteration": 1,
  "variant": "S8v2_StochasticSmaTrend",
  "change": "Added price > SMA200 as first required condition",
  "rationale": "Filter counter-trend crosses. Reversion-in-uptrend hypothesis.",
  "baseline": {
    "train": {"trades": 3602, "win_rate": 0.571, "expectancy": 0.166},
    "test":  {"trades": 1000, "win_rate": 0.542, "expectancy": 0.133}
  },
  "variant_result": {
    "train": {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "gate": ""},
    "test":  {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "gate": ""}
  },
  "outcome": "fill in: S8v2_supersedes_S8 | S8v2_no_improvement | S8v2_failed_gate"
}
```

VERIFY:
```python
import json
data = json.load(open("backtesting/validated_strategies.json"))
assert len(data["tuning_log"]) >= 1
assert data["tuning_log"][0]["strategy"] == "S8_StochasticCross"
assert data["tuning_log"][0]["outcome"] != "fill in"
# Exactly one of S8 or S8v2 must be in validated
s8_present   = "S8_StochasticCross"     in data["validated"]
s8v2_present = "S8v2_StochasticSmaTrend" in data["validated"]
assert s8_present != s8v2_present, "exactly one S8 variant must be validated"
print("2.10 ok")
```

CHANGELOG:
```
## YYYY-MM-DD — Task 2.10: S8v2 SMA200 filter comparison
### Added
- backtesting/strategies/s8v2_stochastic_sma_filter.py
- backtesting/run_s8_comparison.py
### Modified
- backtesting/validated_strategies.json: tuning_log entry added
### Result
- S8v2 train: XXXt WR=XX% E=XX — PASS/FAIL
- S8v2 test:  XXXt WR=XX% E=XX — PASS/FAIL
- Outcome: [S8v2_supersedes_S8 | S8v2_no_improvement | S8v2_failed_gate]
### Registry change
- [S8v2 registered in place of S8] OR [S8 kept unchanged]
```

---

## Phase 2 complete checklist

- [ ] base.py has Condition, RiskLevels, StrategyResult, upgraded BaseStrategy
- [ ] base.py has _stop_is_valid() guard and StrategyResult.ticker field
- [ ] registry.py exists with all strategies registered
- [ ] StrategyScanner.scan() runs without errors on any ticker
- [ ] All strategies have evaluate() + _check_conditions() + _compute_risk()
- [ ] All _compute_risk() implementations call _stop_is_valid() and return None if False
- [ ] All strategies: every should_enter() condition has a matching Condition in _check_conditions()
- [ ] S8 _check_conditions() explicitly includes SMA200 uptrend condition
- [ ] run_backtest.py uses SQLiteProvider (reads from local DB, not yfinance)
- [ ] run_backtest.py completes in under 5 minutes
- [ ] validated_strategies.json has real train + test results filled in
- [ ] validated_strategies.json tuning_log has S8 comparison entry
- [ ] Exactly one S8 variant in validated (either S8 or S8v2, not both)
- [ ] S10 in pending with classification note
- [ ] CHANGELOG.md has all task entries with real numbers
- [ ] `python scripts/smoke_test.py` passes
- [ ] `git diff app/` shows zero changes to existing app/ files
- [ ] `python -m pytest tests/` — all original tests passing