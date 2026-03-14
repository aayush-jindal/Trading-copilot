# Changelog

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
