# Backtesting Framework — Overview

## What is this?

Trading Copilot already shows you technical analysis signals and AI commentary for any stock. The backtesting framework answers a different question:

> *"If I had followed this strategy's rules every day for the last 5 years, how would I have actually done?"*

It replays history bar by bar, applies strategy rules to each day's data, tracks every simulated trade, and produces statistics you can trust — win rate, average profit/loss per trade, maximum drawdown, and expectancy.

---

## How it fits into the project

```
Trading Copilot (existing)
├── app/services/ta_engine.py     ← computes all technical signals (FROZEN — never modified)
├── app/services/market_data.py   ← fetches/caches price data (FROZEN)
└── app/routers/, frontend/       ← the live web app

Backtesting (new, layered on top)
└── backtesting/
    ├── data.py          ← downloads historical data directly from Yahoo Finance
    ├── signals.py       ← wraps ta_engine, computes signals for any slice of history
    ├── base.py          ← BaseStrategy ABC + Trade + StopConfig dataclasses
    ├── engine.py        ← bar-by-bar replay engine (no look-ahead bias)
    ├── results.py       ← statistics, summary table, CSV export, gate check
    ├── run_backtest.py  ← (Task 2.4) runs all strategies, prints results, exports CSVs
    └── strategies/
        ├── s1_trend_pullback.py   ← S1: reads swing_setup.verdict from ta_engine
        ├── s2_rsi_reversion.py    ← S2: RSI oversold crossover + SMA200 + BB filter
        └── s3_bb_squeeze.py       ← S3: Bollinger Band squeeze breakout
```

The backtesting framework is **read-only** with respect to the rest of the app. It calls `ta_engine.py` functions but never modifies them. The live app is unaffected.

---

## Core concepts

### No look-ahead bias

On each bar `i`, the engine only feeds data up to and including that bar into the signal engine:

```python
window = df.iloc[:i + 1]   # only past data visible
snapshot = SignalEngine().compute(window)
```

This means the strategy on March 15 cannot see what happens on March 16. Results reflect what would actually have been tradeable.

### R-multiples

Profit and loss are expressed in **R-multiples** — units of initial risk. If you risk $1 per share (entry − stop) and make $2, that's +2R. If you hit your stop, that's −1R. This makes strategies comparable regardless of position sizing.

- **Expectancy** = average R across all trades. Positive expectancy means the strategy is profitable on average.
- **Gate condition**: ≥ 30 trades AND expectancy > 0 over the test universe and window.

### Trade lifecycle

```
Bar i: compute signals
  → if flat:  should_enter()? → yes → open trade, record entry + stop + target
  → if in trade:
       close ≤ stop_loss  → exit, reason="stop",     pnl_r = negative
       close ≥ target_1   → exit, reason="target_1", pnl_r = positive
       should_exit()?     → exit, reason="signal",   pnl_r = varies
```

---

## The three strategies

### S1 — TrendPullbackStrategy (`s1_trend_pullback.py`)

**Idea:** Buy when a stock in an established uptrend pulls back to support and shows a reversal signal.

**How it works:** Reads the `swing_setup.verdict` field directly from `ta_engine`. That field is already the result of a 100-point scoring system that checks trend confirmation, ADX strength, RSI pullback quality, proximity to support, OBV, candlestick reversal patterns, and a 3-bar breakout trigger. The strategy simply asks: did the engine say `"ENTRY"`?

- **Entry:** `swing_setup.verdict == "ENTRY"`
- **Stop:** taken from `swing_setup.risk.stop_loss` (support − 1×ATR)
- **Target:** taken from `swing_setup.risk.target` (nearest resistance)
- **Exit:** RSI ≥ 65 (overbought) or price reaches nearest resistance

**Results on full universe 2019–2024:**

| Ticker | Trades | Win% | Expectancy |
|--------|--------|------|------------|
| SPY    | 38     | 79%  | +0.090R    |
| QQQ    | 26     | 85%  | +0.195R    |
| AAPL   | 20     | 85%  | +0.251R    |
| MSFT   | 17     | 94%  | +0.246R    |
| GOOGL  | 17     | 77%  | −0.003R    |
| AMZN   | 9      | 67%  | +0.040R    |
| JPM    | 24     | 79%  | +0.129R    |
| XLF    | 29     | 69%  | +0.002R    |
| XLK    | 22     | 73%  | +0.140R    |
| XLE    | 5      | 100% | +0.581R    |
| GLD    | 19     | 79%  | +0.075R    |

**Aggregate: 226 trades · Expectancy +0.1262R**
- **Gate: PASS ✓**

---

### S2 — RSIMeanReversionStrategy (`s2_rsi_reversion.py`)

**Idea:** Buy when a stock that was oversold starts recovering, but only if the bigger trend is still up.

**How it works:** Waits for RSI to cross back above 30 (not just be below it — the crossover catches the actual turn). Requires the stock to still be above its 200-day moving average (no catching falling knives in a bear market) and price to still be near the lower Bollinger Band.

- **Entry:** RSI crosses above 30 AND price above SMA200 AND BB position < 20
- **Stop:** entry − 1.5×ATR
- **Target:** BB middle band (mean reversion target) or entry + 2×ATR fallback
- **Exit:** RSI ≥ 55 (mean reversion complete)

**Results on full universe 2019–2024:**
- 12 trades total across 11 tickers · Aggregate expectancy −0.2853R
- **Gate: FAIL** — RSI rarely dips below 30 for large-cap indices and ETFs; only 12 signals in 5 years
- Positive expectancy on SPY (+0.197R) and JPM (+0.135R) where trades occur, but trade count far below the 30-trade gate

---

### S3 — BBSqueezeStrategy (`s3_bb_squeeze.py`)

**Idea:** Buy when a period of low volatility (the "squeeze") resolves with a strong upside breakout.

**How it works:** A Bollinger Band squeeze is when the bands compress to their narrowest range in 120 days — volatility has dried up. When the squeeze releases and price simultaneously breaks above the upper band on high volume, that's a potential explosive move. The SMA200 filter ensures we only take long-side breakouts in uptrends.

- **Entry:** BB squeeze on previous bar AND no squeeze now AND price > upper band AND volume ≥ 1.5× average AND price above SMA200
- **Stop:** BB lower band at entry bar
- **Target:** entry + 2×ATR
- **Exit:** price closes back below upper band (false breakout) or OBV trend turns FALLING

**Results on full universe 2019–2024:**
- 22 trades total across 11 tickers · Aggregate expectancy +0.0298R
- **Gate: FAIL** — trade count (22) below the 30-trade minimum; positive expectancy but insufficient sample size
- Best performers: GOOGL 2 trades WR=100% E=+0.235R, GLD 3 trades WR=67% E=+0.083R
- Core constraint: `price > bb_upper` at the exact moment a squeeze resolves is uncommon; 32 resolutions on SPY but only 1 passes all entry filters

---

## Test universe and window

All strategies are evaluated on:

| Universe | Window |
|----------|--------|
| SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, JPM, XLF, XLK, XLE, GLD | 2019-01-01 → 2024-01-01 (5 years) |

This gives each strategy exposure to: the 2020 COVID crash and recovery, the 2021 bull run, the 2022 rate-hike bear market, and the 2023 recovery. A strategy that only works in bull markets will be exposed.

---

## Phase progress

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Framework skeleton — data, signals, engine, results | **Complete** |
| **Phase 2** | Three strategies + full backtest run | **Complete — S1 passes gate** |
| **Phase 3** | TBD — likely strategy refinement or UI integration | Not started |

### Phase 2 gate

To advance to Phase 3, each strategy must show ≥ 30 trades and positive expectancy on the full universe. Current status:

| Strategy | Trades | Agg. Expectancy | Gate |
|----------|--------|-----------------|------|
| S1 TrendPullback | 226 | +0.1262R | **PASS ✓** |
| S2 RSIMeanReversion | 12 | −0.2853R | **FAIL ✗** |
| S3 BBSqueeze | 22 | +0.0298R | **FAIL ✗** |

Universe: SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, JPM, XLF, XLK, XLE, GLD · Window: 2019–2024

---

## Running a backtest

```bash
# Inside the Docker container
docker-compose -f docker/docker-compose.yml exec api python3 -c "
from backtesting.strategies.s1_trend_pullback import TrendPullbackStrategy
from backtesting.engine import BacktestEngine
from backtesting.results import ResultsAnalyzer

logs = BacktestEngine().run(
    TrendPullbackStrategy(),
    universe=['SPY', 'QQQ', 'AAPL'],
    start='2019-01-01',
    end='2024-01-01',
)
ResultsAnalyzer(logs).summary()
"

# Run the full backtest script (Task 2.4)
docker-compose -f docker/docker-compose.yml exec api python3 backtesting/run_backtest.py
```

---

## Key design rules

1. **Never modify `ta_engine.py`** — it is the source of truth for all signal logic
2. **No look-ahead bias** — each bar only sees `df.iloc[:i+1]`
3. **Strategies are thin** — they read signal outputs, they do not recompute signals
4. **R-multiples only** — position sizing is abstracted away; results are scale-independent
