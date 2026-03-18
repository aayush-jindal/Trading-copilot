# Changelog

---

## 2026-03-18 — Task 2.10: S8v2 comparison, SQLiteProvider, run_backtest SQLite-only

### Added
- `backtesting/strategies/s8v2_stochastic_sma_filter.py` — S8 variant with SMA200 uptrend gate added as the first required condition in `_check_conditions()`. Class: `StochasticSmaTrendStrategy`, name = `S8v2_StochasticSmaTrend`. Not registered in registry (see decision below).
- `backtesting/data.py` — added `SQLiteProvider`: read-only DataProvider that reads from local SQLite cache only, no network calls. Raises `ValueError` if ticker/window not in cache. Used by all future backtest runs.
- `backtesting/run_s8_comparison.py` — standalone comparison script: runs S8 + S8v2 across full universe (train+test) using `SQLiteProvider`, applies decision rules, writes tuning_log entry to `validated_strategies.json`.

### Changed
- `backtesting/run_backtest.py` — `_run_one()` now uses `SQLiteProvider()` instead of `YFinanceProvider`. All future backtest runs read from local SQLite cache only; no yfinance network calls during backtesting.
- `backtesting/validated_strategies.json` — added S8v2 result + tuning_log entry; restored S8 to VALIDATED with corrected stats; restored S10 to PENDING with correct stats (Docker had stale artefact data).

### S8 vs S8v2 Comparison Results (2026-03-18)
- 80 jobs (39 tickers × 2 phases), 2 Docker workers, SQLite-only — no network calls
- S8v2 result identical to S8 in every metric: S8 `should_enter()` already gates on `price_vs_sma200 == "above"`, so the SMA200 condition added in S8v2 is redundant

| Strategy | Train | Test | Decision |
|---|---|---|---|
| S8_StochasticCross | 3602t WR=57.1% E=+0.166R | 1000t WR=54.2% E=+0.133R | VALIDATED (unchanged) |
| S8v2_StochasticSmaTrend | 3602t WR=57.1% E=+0.166R | 1000t WR=54.2% E=+0.133R | NOT_REGISTERED (no improvement) |

**Decision: NO_IMPROVEMENT** — S8 remains in registry. S8v2 is not registered.

---

## 2026-03-17 — Engine batch optimization + full backtest results

### Changed
- `backtesting/engine.py` — major performance rewrite
  - Added `run_batch(strategies, ticker, start, end)`: fetches data once per ticker and computes `SignalSnapshot` once per bar shared across all strategies (~9× speedup vs calling `run()` separately per strategy)
  - Added `_run_ticker_batch()`: inner loop that replays all strategies against the same pre-computed snapshot stream
  - Extracted `_manage_trade()` and `_force_close()` helpers to eliminate code duplication
  - Fixed rolling lookback window (`_DAILY_LOOKBACK=500`, `_WEEKLY_LOOKBACK=104`) — prevents O(n²) signal recomputation (was growing `df.iloc[:i+1]` → now fixed 500-bar window)
  - `run()` single-strategy path kept for backward compatibility
- `backtesting/run_backtest.py` — restructured job parallelism
  - Jobs changed from `(strategy, ticker, phase)` → `(ticker, phase)` with all 7 strategies batched inside each job
  - 560 jobs → 80 jobs; each job runs 7 strategies on the same ticker with shared signals
  - Progress output now shows per-ticker completion with strategy log count
  - Abort threshold adjusted to `n_done >= 10` (fewer jobs)

### Results — Full backtest run 2026-03-17
- 80 jobs (40 tickers × 2 phases, 7 strategies batched), 2 Docker workers
- Total wall time: ~30 minutes (vs estimated 10+ hours before optimization)
- 39/40 tickers processed (SQ permanently unavailable from yfinance)

| Strategy | Train | Test | Verdict |
|---|---|---|---|
| S1_TrendPullback | 2903t WR=78.6% E=+0.109R | 685t WR=75.5% E=+0.068R | VALIDATED |
| S2_RSIMeanReversion | 171t WR=50.3% E=+0.099R | 49t WR=59.2% E=+0.383R | VALIDATED |
| S3_BBSqueeze | 263t WR=46.4% E=+0.032R | 70t WR=50.0% E=+0.060R | VALIDATED |
| S7_MACDCross | 1186t WR=76.6% E=+0.365R | 338t WR=77.2% E=+0.380R | VALIDATED |
| S8_StochasticCross | 3602t WR=57.1% E=+0.166R | 1000t WR=54.2% E=+0.133R | VALIDATED |
| S9_EMACross | 858t WR=70.2% E=+0.105R | 247t WR=67.2% E=+0.019R | VALIDATED |
| S10_GoldenCrossPullback | 158t WR=29.8% E=+0.012R | 40t WR=35.0% E=-0.010R | PENDING |

- S8 reinstated as VALIDATED — `_stop_is_valid()` guard corrected +662R artefact to realistic +0.166R
- S10 PENDING — test expectancy slightly negative (-0.010R), regime-sensitive

### Updated
- `backtesting/validated_strategies.json` — updated with 2026-03-17 run results; S8 VALIDATED, S10 PENDING, S10 removed from VALIDATED list

---

## 2026-03-16 — Cache validator, retry logic, abort-on-failure

### Added
- `backtesting/validate_cache.py` — pre-run health check script
  - `check_db_integrity()`: SQLite `PRAGMA integrity_check` + table/column verification
  - `prefetch_universe()`: downloads every ticker × (train, test) window, stores in cache
  - `report()`: per-ticker row count table, flags tickers below `MIN_TRAIN_ROWS=200` / `MIN_TEST_ROWS=100`
  - Gate: allows ≤ 3 tickers with insufficient data (newly listed / delisted); exits 0 = OK, 1 = DB corrupt, 2 = too many missing tickers
  - Run: `python backtesting/validate_cache.py`

### Modified
- `backtesting/data.py`
  - `_download_raw()`: retries up to 3× with 2s back-off on transient yfinance errors; returns empty DataFrame for "no data in window" (not a network error); raises `DataFetchError` only after all retries are exhausted
  - Added `DataFetchError(RuntimeError)` — distinct error class so callers can tell data failures apart from other exceptions
- `backtesting/run_backtest.py`
  - Pre-flight: runs `validate_cache.py` as a subprocess; aborts (`sys.exit`) if it returns non-zero
  - Abort-on-failure: counts failed jobs as they complete; if > 15% fail after 20+ samples, shuts down the `ProcessPoolExecutor` immediately and exits with code 3
  - Failed jobs now print `FAIL` (not `SKIP`) and show full 70-char error

---

## 2026-03-16 — SQLite data cache added to backtesting

### Added
- `backtesting/cache.py` — `DataCache` class backed by SQLite (`backtesting/ohlcv.db`)
  - Table: `ohlcv (ticker, date, interval, open, high, low, close, volume)` — PK (ticker, date, interval)
  - WAL journal mode for safe concurrent worker reads/writes
  - `coverage(ticker, interval)` — returns (min_date, max_date) of cached rows
  - `load(ticker, start, end, interval)` — returns cached DataFrame
  - `upsert(ticker, df, interval)` — INSERT OR REPLACE all rows

### Modified
- `backtesting/data.py` — `YFinanceProvider` now checks cache before yfinance
  - On first fetch: downloads from yfinance, stores in DB
  - On subsequent fetches: reads from DB (zero network calls)
  - On range extension: fetches only the missing gap, appends to DB
  - `_download_raw()` never raises — returns empty DataFrame on failure (errors logged by yfinance, not fatal)
- `.gitignore` — added `backtesting/ohlcv.db`

### Docker workflow for cache persistence
```bash
# Before each run: copy cached DB into container
docker cp backtesting/ohlcv.db $(docker-compose -f docker/docker-compose.yml ps -q api):/app/backtesting/
# (already included in: docker cp backtesting/ container:/app/)

# After each run: pull updated DB back to host
docker cp $(docker-compose -f docker/docker-compose.yml ps -q api):/app/backtesting/ohlcv.db ./backtesting/
```
Second and subsequent backtest runs will complete in minutes instead of hours.

---

## 2026-03-15 — Task 2.9 (corrected): Aggregation bug fixed, real results recorded

### Bug fixed
- `backtesting/run_backtest.py` — `_aggregate()` was using a dict comprehension on per-ticker stats, keeping only the last ticker per strategy name. Fixed with proper per-strategy aggregation (weighted expectancy by trade count across all tickers).

### Corrected results (from train_results.csv / test_results.csv)
Train / Test / Verdict:
- S1  TrendPullback:      2912t WR=78.6% E=+0.110R /  699t WR=75.3% E=+0.060R  — **VALIDATED**
- S2  RSIMeanReversion:    171t WR=50.3% E=+0.099R /   49t WR=59.2% E=+0.383R  — **VALIDATED**
- S3  BBSqueeze:           258t WR=45.7% E=+0.031R /   70t WR=50.0% E=+0.060R  — **VALIDATED**
- S7  MACDCross:          1175t WR=76.5% E=+0.359R /  329t WR=77.8% E=+0.393R  — **VALIDATED**
- S8  StochasticCross:    3957t WR=47.2% E=+662R   / 1113t WR=44.6% E=+141R   — RETIRED (R artefact)
- S9  EMACross:            849t WR=69.8% E=+0.169R /  247t WR=66.8% E=+0.025R  — **VALIDATED**
- S10 GoldenCrossPullback: 160t WR=37.5% E=+1.671R /   40t WR=52.5% E=+2.430R  — **VALIDATED**

### S8 retired
- S8 expectancy is a calculation artefact: `nearest_support` occasionally sits within ticks of entry price, making `entry - stop` near-zero and inflating R values to hundreds. Actual win rate (47%) with realistic stops would yield negative expectancy. Removed from validated list.

### Updated
- `backtesting/validated_strategies.json` — 6 strategies validated, S8 retired, real trade counts recorded

---

## 2026-03-15 — Task 2.9 (revised): Expanded backtest — 40 tickers, train/test split

### Modified
- `backtesting/run_backtest.py` — complete rewrite: 40-ticker universe across 7 categories, 80/20 train/test split (2005→2021 train, 2021→2026 test), per-ticker IPO start dates (TSLA/META/V/SQ/SHOP/XLRE), two-stage gate (train ≥30t E>0, test ≥20t E>0), `ProcessPoolExecutor`
- `backtesting/validated_strategies.json` — updated with train/test results, tuning classifications, tuning_log, notes

### Universe (40 tickers)
- Broad market ETFs: SPY, QQQ, IWM, DIA, EEM, EFA
- Sector ETFs: XLF, XLK, XLE, XLV, XLY, XLI, XLB, XLP
- Large-cap tech: AAPL, MSFT, GOOGL, AMZN, NVDA, AMD, TSLA, META, NFLX
- Blue chips: JPM, BAC, XOM, V, MA, UNH, HD
- Mid-cap growth: CRM, SQ, SHOP, BRK-B
- Commodities: GLD, SLV, USO, TLT
- Real estate: VNQ, XLRE

### Train window: per-ticker max(2005-01-01, ipo) → 2021-01-01
### Test window: 2021-01-01 → 2026-01-01
### Jobs: 560 (7 strategies × 40 tickers × 2 phases) | Workers: 2 | Runtime: ~3.5 hours

### Results — Train / Test / Verdict
- S1  TrendPullback:         94t WR=85.1% E=+0.171R /  11t WR=72.7% E=+0.094R  — PENDING (Level 1: test window needs more equity-style tickers)
- S2  RSIMeanReversion:       7t WR=14.3% E=-1.129R /   2t WR=0.0%  E=-1.214R  — FAILED  (Level 1: RSI<30 rarely fires in ETF-heavy universe)
- S3  BBSqueeze:              6t WR=50.0% E=-0.076R /   1t WR=0.0%  E=-0.222R  — FAILED  (Level 1: squeeze + breakout rare in diversified universe)
- S7  MACDCross:             37t WR=78.4% E=+0.418R /  13t WR=69.2% E=+0.283R  — PENDING (Level 1: both windows positive, test needs more tickers)
- S8  StochasticCross:       96t WR=46.9% E=+5.083R /  24t WR=29.2% E=+3.078R  — VALIDATED (caution: high expectancy; contradicts prior 18-ticker -2.35R result)
- S9  EMACross:              21t WR=66.7% E=+0.195R /   3t WR=33.3% E=-0.291R  — FAILED  (Level 1 borderline: 21 train trades; prior run had 117t passing)
- S10 GoldenCrossPullback:    7t WR=28.6% E=+56.94R /   1t WR=0.0%  E=-0.923R  — FAILED  (Level 1: too few trades; +56.94R is artefact of tiny SMA50 stop)

### Issues noted
- SQ: all 14 download jobs failed (yfinance "possibly delisted") — remove from future runs
- Low trade counts likely due to: diversified universe (bonds/REITs rarely trigger equity setups) + possible yfinance rate limiting during parallel downloads

### Smoke test
- 33/33 checks passed (run separately, app/ files unchanged)

---

## 2026-03-14 — Task 2.9: Full backtest run — parallelized

### Modified
- `backtesting/run_backtest.py` — complete rewrite: `ProcessPoolExecutor`, updated universe (18 tickers), all 7 strategies, per-strategy CSV export, gate summary
- `backtesting/engine.py` — extended `_enter_kwargs` detection to include `_prev_k`, `_prev_ema9`, `_bars_since_cross` so S8/S9/S10 receive correct per-ticker state

### Added
- `backtesting/validated_strategies.json` — strategies passing gate recorded with real numbers

### Performance
- Jobs: 126 (7 strategies × 18 tickers)
- Workers: 2 Docker CPUs
- Window: 2019-01-01 to 2024-01-01

### Results
- S1_TrendPullback:        307 trades  WR=79.2%  E=+0.1034R  — **PASS**
- S2_RSIMeanReversion:      19 trades  WR=50.0%  E=-0.0581R  — FAIL (< 30 trades)
- S3_BBSqueeze:             32 trades  WR=58.3%  E=+0.1066R  — **PASS**
- S7_MACDCross:            124 trades  WR=76.7%  E=+0.4076R  — **PASS**
- S8_StochasticCross:      519 trades  WR=42.5%  E=-2.3476R  — FAIL (negative expectancy)
- S9_EMACross:             117 trades  WR=73.9%  E=+0.2197R  — **PASS**
- S10_GoldenCrossPullback:  20 trades  WR=31.9%  E=+1.8312R  — FAIL (< 30 trades)

### Smoke test
- 33/33 checks passed

---

## 2026-03-14 — Task 2.8: S8, S9, S10 strategies built

### Added
- `backtesting/strategies/s8_stochastic_cross.py` — `StochasticCrossStrategy` (`type = "reversion"`)
- `backtesting/strategies/s9_ema_cross.py` — `EMACrossStrategy` (`type = "trend"`)
- `backtesting/strategies/s10_golden_cross_pullback.py` — `GoldenCrossPullbackStrategy` (`type = "trend"`)

### Modified
- `backtesting/strategies/registry.py` — S8, S9, S10 registered (registry now has 7 strategies)

### Verified
```
Registry has 7 strategies
  S8_StochasticCross: NO_TRADE score=33
  S9_EMACross: WATCH score=50
  S10_GoldenCrossPullback: WATCH score=50
2.8 ok
```

---

## 2026-03-14 — Task 2.7: S7 MACDCrossStrategy built

### Added
- `backtesting/strategies/s7_macd_cross.py` — `MACDCrossStrategy` (`type = "trend"`, 4 conditions: MACD bullish crossover, SMA200, RSI 40-60, weekly BULLISH)

### Modified
- `backtesting/strategies/registry.py` — S7 registered (registry now has 4 strategies)

### Verified
```
S7_MACDCross: NO_TRADE score=25
Registry size: 4
2.7 ok
```

---

## 2026-03-14 — Task 2.6: S3 BBSqueezeStrategy upgraded with factory pattern

### Modified
- `backtesting/strategies/s3_bb_squeeze.py` — added `type = "breakout"`, updated imports; added `_check_conditions()` (4 conditions: squeeze resolved, price above BB upper, volume ≥ 1.5×, SMA200), `_compute_risk()` (BB lower stop, 2×ATR target), `evaluate()`; `should_enter`/`should_exit`/`get_stops` unchanged
- `backtesting/strategies/registry.py` — `BBSqueezeStrategy` registered (registry now has 3 strategies)

### Verified
```
Active strategies: ['S2_RSIMeanReversion']
S1_TrendPullback: NO_TRADE score=37
S2_RSIMeanReversion: NO_TRADE score=0
S3_BBSqueeze: NO_TRADE score=0
Registry size: 3
2.6 ok
```

---

## 2026-03-14 — Task 2.5: S2 RSIMeanReversionStrategy upgraded with factory pattern

### Modified
- `backtesting/strategies/s2_rsi_reversion.py` — added `type = "reversion"`, updated imports; added `_check_conditions()` (3 conditions: SMA200, RSI cross above 30, BB position < 20), `_compute_risk()` (1.5×ATR stop, BB-middle target), `evaluate()`; `should_enter`/`should_exit`/`get_stops` unchanged
  - Fixed: `distance_from_sma200_pct` can be `None` — guarded with `or 0`
- `backtesting/strategies/registry.py` — `RSIMeanReversionStrategy` registered

### Verified
```
S1_TrendPullback: NO_TRADE score=37
S2_RSIMeanReversion: NO_TRADE score=0
Registry size: 2
2.5 ok
```

---

## 2026-03-14 — Task 2.4: StrategyScanner built

### Added
- `backtesting/scanner.py` — `StrategyScanner.scan(ticker, account_size, risk_pct)`
  - Fetches last 500 days of daily data via `YFinanceProvider`
  - Computes `SignalSnapshot` via `SignalEngine`
  - Evaluates all strategies in `STRATEGY_REGISTRY`
  - Filters out `NO_TRADE` results
  - Computes `position_size = int((account_size * risk_pct) / (entry - stop))` on each remaining result
  - Sorts by score descending

### Verified
```
Scanning SPY...
SPY: 1 strategies with WATCH/ENTRY verdict
  S1_TrendPullback: WATCH score=50
2.4 ok
```

---

## 2026-03-14 — Task 2.3: S1 upgraded with evaluate() factory methods

### Modified
- `backtesting/strategies/s1_trend_pullback.py` — added `_check_conditions()`, `_compute_risk()`, `evaluate()`; `type = "trend"` class attribute added; `should_enter`/`should_exit`/`get_stops` unchanged (used by BacktestEngine)
  - `_check_conditions`: reads `swing["conditions"]` dict, returns 8 `Condition` objects covering uptrend, weekly alignment, ADX, RSI pullback, support proximity, volume, reversal candle, trigger
  - `_compute_risk`: reads `swing["risk"]["stop_loss"]` / `swing["risk"]["target"]` (nested structure), returns `RiskLevels`
  - `evaluate`: calls `_check_conditions` → `_verdict` → `_compute_risk`, returns `StrategyResult`

### Verified
```
S1_TrendPullback NO_TRADE 25
2.3 ok
```

---

## 2026-03-14 — Task 2.2: Strategy registry created

### Added
- `backtesting/strategies/registry.py` — `STRATEGY_REGISTRY` list with `TrendPullbackStrategy()` as sole entry; import of S1 will fail until Task 2.3 adds `evaluate()` — expected and correct per spec

### Verified
- `ast.parse(registry.py)` → syntax valid ✓
- `python3 scripts/smoke_test.py` → 33/33 ✓

---

## 2026-03-14 — Task 2.1: Factory dataclasses added to base.py

### Modified
- `backtesting/base.py` — added `Condition` dataclass (label, passed, value, required); `RiskLevels` dataclass (entry_price, stop_loss, target, risk_reward, atr, entry_zone_low/high, position_size); `StrategyResult` dataclass (name, type, verdict, score, conditions, risk, strategy_instance); upgraded `BaseStrategy` with `type` class attribute, abstract `evaluate()` / `_check_conditions()` / `_compute_risk()`, and default `_verdict()` implementation (all passed→ENTRY, ≥50%→WATCH, <50%→NO_TRADE with proportional score)

### Unchanged
- `engine.py`, `data.py`, `signals.py`, `results.py` untouched

### Verified
- `inspect.isabstract(BaseStrategy)` ✓, `hasattr evaluate/_check_conditions/_compute_risk` ✓
- `python3 scripts/smoke_test.py` → 33/33 ✓

---

## 2026-03-14 — Task 2.4: Full backtest run + gate check

### Added
- `backtesting/run_backtest.py` — runs all three strategies on full universe (SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, JPM, XLF, XLK, XLE, GLD), prints per-strategy summary tables, exports CSVs to `backtest_results/`, prints aggregate gate result and overall phase verdict
- `.gitignore` — added `backtest_results/` entry

### Results (2019-01-01 → 2024-01-01, full universe, Docker)

**S1 TrendPullbackStrategy — 226 trades · Agg. Expectancy +0.1262R — PASS ✓**

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

**S2 RSIMeanReversionStrategy — 12 trades · Agg. Expectancy −0.2853R — FAIL ✗**
- RSI < 30 threshold too conservative for large-cap indices/ETFs; only 12 signals in 5 years

**S3 BBSqueezeStrategy — 22 trades · Agg. Expectancy +0.0298R — FAIL ✗**
- 22 trades but below the 30-trade minimum; positive expectancy but insufficient sample size

### Gate status
- Strategies passing gate : TrendPullback (S1)
- Strategies failing gate : RSIMeanReversion (S2), BBSqueeze (S3)
- **Overall: ADVANCE TO PHASE 3 ✓** (Phase 2 checklist requires at least S1 to pass)

### Verified
- `python3 scripts/smoke_test.py` → 33/33 passed ✓
- `git diff app/` → zero changes ✓

---

## 2026-03-14 — Backtesting documentation updated with Phase 2 results

### Modified
- `docs/backtesting.md` — updated S1/S2/S3 results sections with real numbers from Task 2.4 full run; updated phase progress table to show Phase 2 complete; Phase 2 gate table now has actual trade counts and expectancies

---

## 2026-03-14 — Backtesting documentation

### Added
- `docs/backtesting.md` — layman-friendly overview of the backtesting framework: what it does, how it fits into the project, core concepts (no look-ahead bias, R-multiples, trade lifecycle), per-strategy explanation with results, test universe, phase progress table, running instructions, and key design rules

---

## 2026-03-14 — Task 2.3: S3 BBSqueezeStrategy

### Added
- `backtesting/strategies/s3_bb_squeeze.py` — `BBSqueezeStrategy(BaseStrategy)` with `name = "S3_BBSqueeze"`; entry when BB squeeze resolves (prev_squeeze=True → curr=False) AND price breaks above upper band AND volume_ratio ≥ 1.5 AND price above SMA200; stop = BB lower at entry bar; target = entry + 2×ATR; exit when price closes back below BB upper (false breakout) or OBV trend FALLING; tracks `_prev_squeeze` per ticker

### Key decisions
- Requires squeeze on PREVIOUS bar to catch the actual breakout bar, not mid-squeeze
- Volume filter (≥1.5× avg) reduces false breakouts significantly
- `_prev_squeeze` handled by existing engine state-tracking fix from Task 2.2

### Unchanged
- `app/services/ta_engine.py` untouched

### Verified (SPY+QQQ+AAPL 2019-2024, Docker)
- SPY: 1 trade · WR=0% · E=−0.07R; QQQ: 1 trade; AAPL: 4 trades · WR=50% · E=+0.07R
- Diagnosis: 32 squeeze resolutions on SPY, only 1 passes all three entry filters (price>upper + vol + SMA200). Strict filter by design — will fail gate (documented in Task 2.4)
- `pytest backtesting/tests/` → 1 passed ✓

---

## 2026-03-14 — Task 2.2: S2 RSIMeanReversionStrategy

### Added
- `backtesting/strategies/s2_rsi_reversion.py` — `RSIMeanReversionStrategy(BaseStrategy)` with `name = "S2_RSIMeanReversion"`; entry on RSI crossover above 30 (prev < 30 AND curr ≥ 30) combined with price above SMA200 and BB position < 20; stop = entry − 1.5×ATR; target = BB middle (fallback: entry + 2×ATR); exit on RSI ≥ 55; tracks `_prev_rsi` per ticker

### Modified
- `backtesting/engine.py` — `_run_ticker` now always calls `should_enter` every bar (not only when flat) so `_prev_rsi` / `_prev_squeeze` state stays current through open trades; passes `ticker=` kwarg when strategy has per-ticker state attributes

### Key decisions
- RSI crossover above 30 (not just level) reduces false entries but produces few signals on index ETFs
- SMA200 filter prevents mean reversion trades in downtrends
- BB position < 20 ensures price still near lower band at entry

### Unchanged
- `app/services/ta_engine.py` untouched

### Verified (SPY+QQQ 2019-2024, Docker)
- SPY: 2 trades · WR=50% · E=+0.197R; QQQ: 1 trade · WR=100% · E=+1.367R
- Full universe preview: 12 trades total — will fail Phase 2 gate (gate check in Task 2.4)
- `pytest backtesting/tests/` → 1 passed ✓

---

## 2026-03-14 — Task 2.1: S1 TrendPullbackStrategy

### Added
- `backtesting/strategies/s1_trend_pullback.py` — `TrendPullbackStrategy(BaseStrategy)` with `name = "S1_TrendPullback"`; entry reads `swing_setup.verdict == "ENTRY"` and validates `risk.stop_loss` / `risk.target`; stops taken unchanged from `swing_setup.risk`; exit on RSI ≥ 65 or price ≥ nearest_resistance

### Key decisions
- Entry reads `swing_setup.verdict` directly — zero reimplementation of swing logic
- Stop/target sourced from `swing_setup["risk"]` (nested per actual ta_engine output)
- Phase 2 spec pseudocode shows top-level keys; adapted to match actual ta_engine structure

### Unchanged
- `app/services/ta_engine.py` untouched

### Verified (SPY 2019-01-01 → 2024-01-01, Docker)
- 38 trades · WR=79.0% · AvgR=0.090 · Expectancy=0.090 R · PF=1.866 — **GATE PASS ✓**

---

## 2026-03-14 — Task 1.7: Framework integration test

### Added
- `backtesting/tests/test_framework.py` — `TrivialStrategy` (always enters, never exits on signal, 5% stop / 10% target); `test_framework_wires_together` runs BacktestEngine on SPY 2023 and asserts result is a list with a TradeLog containing `.trades`

### Verified
- `pytest backtesting/tests/test_framework.py -v` → 1 passed in 3.93s ✓ (Docker container)
- `python3 scripts/smoke_test.py` → 33/33 passed ✓

---

## 2026-03-14 — Task 1.6: ResultsAnalyzer

### Added
- `backtesting/results.py` — `StrategyStats` dataclass (strategy_name, ticker, total_trades, win_rate, avg_rr, expectancy, max_drawdown_r, profit_factor); `ResultsAnalyzer` with `compute() -> list[StrategyStats]`, `summary()` (formatted stdout table with gate pass marker), `to_csv(path)`, and `passes_gate(stats) -> bool` (total_trades ≥ 30 AND expectancy > 0)

### Verified
- `hasattr(ResultsAnalyzer, 'passes_gate')` → True ✓
- Docker container exec ✓

---

## 2026-03-14 — Task 1.5: BacktestEngine

### Added
- `backtesting/engine.py` — `TradeLog` dataclass (trades, ticker, strategy_name, start_date, end_date); `BacktestEngine` with `run(strategy, universe, start, end) -> list[TradeLog]` and `_run_ticker`; bar-by-bar replay using `df.iloc[:i+1]` slices; stop/target/signal exit logic with R-multiple P&L; forced close on last bar; weekly DataFrame sliced in sync per bar

### Verified
- `BacktestEngine()` instantiates ✓
- Docker container exec ✓

---

## 2026-03-14 — Task 1.4: BaseStrategy + dataclasses

### Added
- `backtesting/base.py` — `StopConfig` dataclass (entry_price, stop_loss, target_1, target_2, target_3, risk_reward); `Trade` dataclass (ticker, entry/exit dates and prices, exit_reason, pnl_r, signal_snapshot); `BaseStrategy` ABC with abstract `should_enter`, `should_exit`, `get_stops` and concrete `describe()`

### Verified
- `inspect.isabstract(BaseStrategy)` → True ✓
- `hasattr(BaseStrategy, 'should_enter')` → True ✓
- Docker container exec ✓

---

## 2026-03-14 — Task 1.3: SignalEngine + SignalSnapshot

### Added
- `backtesting/signals.py` — `SignalSnapshot` dataclass (price, trend, momentum, volatility, volume, support_resistance, swing_setup, weekly, candlestick); `SignalEngine.compute(df, weekly_df=None)` that calls all `app/services/ta_engine` functions directly in read-only fashion

### Unchanged
- `app/services/ta_engine.py` untouched — called, never modified

### Verified
- `SignalEngine().compute(df)` on SPY 2022–2024: `snap.price > 0`, `"signal" in snap.trend`, `"rsi" in snap.momentum` ✓ (verified inside Docker container)
- `python3 scripts/smoke_test.py` → 33/33 passed ✓

---

## 2026-03-14 — Task 1.2: DataProvider + YFinanceProvider

### Added
- `backtesting/data.py` — `DataProvider` ABC with `fetch_daily` / `fetch_weekly` abstract methods; `YFinanceProvider` implementing both via `yf.download()` with lowercase column normalisation, NaN-close drop, MultiIndex flattening, and ≥100-row guard; `DEFAULT_PROVIDER` singleton

### Unchanged
- `app/services/market_data.py` untouched — backtesting fetches directly via yfinance, no DB required

### Verified
- `fetch_daily("SPY", "2023-01-01", "2024-01-01")` → 252 rows, columns `[open,high,low,close,volume]` ✓
- `python3 scripts/smoke_test.py` → 33/33 passed ✓

---

## 2026-03-14 — Task 1.1: backtesting package skeleton

### Added
- `backtesting/__init__.py` — package root with module docstring describing read-only relationship to ta_engine/market_data
- `backtesting/strategies/__init__.py` — docstring-only init for strategy subpackage
- `backtesting/tests/__init__.py` — empty init for test package
- `backtesting/README.md` — one-paragraph description: purpose, read-only TA engine relationship, three planned strategies (swing-pullback, trend-following, mean-reversion)

### Unchanged
- All existing `app/` files untouched (`git diff app/` clean)

### Verified
- `python3 -c "import backtesting; print('ok')"` → ok
- `python3 scripts/smoke_test.py` → 33/33 checks passed

---

## 2026-03-13 — Options Scanner added as tab on Analysis homepage

### Modified
- `frontend/src/pages/OptionsPage.tsx` — extracted scanner body into exported `OptionsContent` component (stateful, no header); `OptionsPage` now wraps it with its own header for the standalone `/options` route
- `frontend/src/pages/AnalysisPage.tsx` — imported `OptionsContent`, added `activeTab` state, rendered a two-tab bar ("Analysis" / "Options Scanner") at the top of `<main>`, wrapped existing analysis content in the analysis tab fragment; removed the standalone "Options" nav button (replaced by tab)

The options scanner is now reachable directly from the homepage via the tab bar without leaving the page. The `/options` route still works as a standalone page.

---

## 2026-03-13 — Options scanner UI wired into app navigation

### Added
- `frontend/src/pages/OptionsPage.tsx` — already created; route and nav link now wired
- `frontend/src/App.tsx` — added `import OptionsPage` and `<Route path="/options">` protected route
- `frontend/src/pages/AnalysisPage.tsx` — added "Options" nav button in header alongside "Watchlist", navigates to `/options`

The options scanner is now fully accessible in the UI at `/options`. No other pages were modified.

---

## 2026-03-13 — Options opportunity scanner integrated as service

The standalone `options_scanner` project has been migrated into Trading Copilot as a first-class service. It is fully wired into TC's infrastructure: DB-backed market data, full TA engine, existing AI provider configuration, and the knowledge base RAG pipeline.

### Added

#### `app/services/options/` (new package)
Complete options scanner service. All files are described below.

##### `app/services/options/config.py`
Options-specific settings loaded from environment variables with defaults. Defines: `RISK_FREE_RATE`, `MC_NUM_PATHS`, `MC_NUM_STEPS`, `MC_SEED`, `OPTION_STOP_PCT`, `BIAS_THRESHOLD`, `OUTLOOKS` (DTE windows per outlook), and `PRICING` (token cost rates per provider). No new required env vars — all have sensible defaults. Optional overrides prefixed `OPTIONS_*`.

##### `app/services/options/scanner.py`
Core orchestrator. Replaces the standalone `scanner/scanner.py` and `data/ta_signals.py`. Key changes from the standalone version:
- Uses `app.services.market_data.get_or_refresh_data` (DB-cached yfinance) instead of direct yfinance calls — data is shared with TC's existing analysis pipeline.
- Uses `app.services.ta_engine.analyze_ticker` (TC's full TA engine: 200+ bars, weekly trend, candlestick patterns, swing setup) instead of the stripped-down standalone TA.
- Includes `_adapt_signals()` — a translation layer that adds the boolean flag keys the scanner's bias detector and opportunity builder expect, computed from TC's string-comparison and value-based signal format. Also computes `hist_vol` (20-day annualised log-return std) and `atr_percentile` (rolling ATR rank) which are not in TC's volatility output.
- Derives `next_resistance` / `next_support` from TC's `swing_highs` / `swing_lows` ranked lists.
- Calls `tools.knowledge_base.strategy_gen.generate_strategies(ticker)` directly (same-process import — no HTTP, no sys.path shim needed within TC).

##### `app/services/options/bias_detector.py`
Unchanged from standalone scanner. Pure scoring logic — no external dependencies. Scores 14 TA conditions to classify direction as BULLISH / BEARISH / NEUTRAL_HIGH_IV / NEUTRAL_LOW_IV.

##### `app/services/options/strategy_selector.py`
Unchanged logic from standalone scanner. Import path updated: `from app.services.options.config import OUTLOOKS, RISK_FREE_RATE`. Maps `(bias, outlook)` → strategy, selects strikes anchored to S/R levels, returns full leg spec for every strategy type including all 4 iron condor legs.

##### `app/services/options/opportunity_builder.py`
Unchanged logic from standalone scanner. Import paths updated to TC package paths. Builds fully-priced opportunity dict: prices every leg individually with Black-Scholes, sums net premium/Greeks, computes credit/debit-aware exit and stop levels, runs Monte Carlo jump-diffusion on the primary leg, runs American LSMC for puts.

##### `app/services/options/formatter.py`
Verbatim copy from standalone scanner. Renders terminal-style bordered ASCII blocks per ticker. Used by the API's `include_formatted` parameter to return human-readable output alongside the JSON data.

##### `app/services/options/ai_narrative.py`
Adapted from standalone scanner. Replaced `ai_provider.complete()` with direct Anthropic / OpenAI SDK calls using TC's `SYNTHESIS_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` from `app.config`. No new env vars. The system prompt instructs the model to incorporate knowledge base strategies when present and note alignment or conflict with the quantitative scan output.

##### `app/services/options/pricing/` (new sub-package)
Pricing wrapper and bundled source.

`pricing/pricer.py` — identical interface to the standalone scanner's pricer. Adds `pricing/src/` to `sys.path` (local shim to the bundled source) instead of pointing to the external State_Estimators repository. Exposes: `price_bs`, `price_mc`, `get_vol_surface`, `reprice_at`.

`pricing/src/` — verbatim copy of the relevant pricing source from `State_Estimators/misc/stonks/options/src/`:
- `models/black_scholes.py` — Black-Scholes price + Greeks (Delta, Gamma, Theta, Vega, Rho)
- `monte_carlo/gbm_simulator.py` — GBM path simulation + `run_monte_carlo` orchestrator (jump-diffusion, GARCH, American LSMC)
- `monte_carlo/jump_diffusion.py` — Merton jump-diffusion path simulator
- `monte_carlo/american_mc.py` — Longstaff-Schwartz LSMC for American options
- `monte_carlo/risk_metrics.py` — VaR, CVaR, distribution stats
- `monte_carlo/garch_vol.py` — GARCH(1,1) fitting + conditional vol path simulation
- `monte_carlo/mc_greeks.py` — bump-and-reprice MC Greeks (Common Random Numbers)
- `analytics/vol_surface.py` — live IV surface from yfinance option chains

The `analytics/__init__.py` is intentionally minimal (exports only `vol_surface`) since the other analytics modules (simulations, visualization, scenario) are not needed and were not bundled.

**Why bundle instead of import from State_Estimators:** TC is a deployable Docker service. Requiring a sibling repository to exist at a hardcoded path breaks containerised deployment. Bundling makes TC self-contained.

#### `app/routers/options.py`
New FastAPI router under prefix `/options` with two endpoints:
- `POST /options/scan` — scans a list of tickers. Request body: `tickers`, `settings`, `include_ai` (default true), `include_formatted` (default false). Response: `results[]` + optional `ai_narrative`.
- `GET /options/scan/{ticker}` — single-ticker convenience endpoint. Query params: `include_formatted`, `risk_free_rate`.

Both endpoints are JWT-protected (same as `/analysis`, `/synthesis`).

#### `docs/options_scanner.md`
Full system documentation: architecture diagram, file structure, signal adapter key mapping table, strategy/bias logic tables, pricing model descriptions, exit/stop framework, API reference with example request/response, configuration guide, knowledge base integration notes, pricing bundle rationale, and authentication notes.

### Modified

#### `app/main.py`
Added `options` to the router imports and registered `options.router` under JWT authentication middleware alongside the other protected routes.

#### `requirements.txt`
Added `numpy` (was a transitive dep; now explicitly declared) and `matplotlib` (required by `pricing/src/analytics/vol_surface.py` for `plot_vol_surface`; imported at module load with `matplotlib.use('Agg')` so it is safe in a server context).

---
