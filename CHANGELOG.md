# Changelog

---

## 2026-04-10 — Frontend Update: Chain Scanner UI

- [2026-04-10] Modified: frontend/src/types/index.ts — Fixed knowledge_strategies type from `string | null` to `unknown` (Task 1)
- [2026-04-10] Modified: frontend/src/types/index.ts — Added chain scanner types: ChainSignal, ChainSignalLeg, StrategyRecommendation, PricedStrategy, ChainScanResponse (Task 2)
- [2026-04-10] Modified: frontend/src/api/client.ts — Added chainScan() API client function for GET /options/chain-scan (Task 3)
- [2026-04-10] Created: frontend/src/components/ChainScannerPanel.tsx — Chain scanner UI with signal cards, IV regime badges, conviction scores, edge metrics, priced strategies, sorting (Task 4)
- [2026-04-10] Modified: frontend/src/pages/AnalysisPage.tsx — Added "Chain Scanner" as third tab alongside Analysis and Options (Task 5)
- [2026-04-10] No change: frontend/src/pages/OptionsPage.tsx — Standalone /options route works after 500 fix, kept as-is (Task 6)

---

## 2026-04-10 — Nightly Cron: Rate Limit Handling

- [2026-04-10] Modified: app/services/options/chain_scanner/providers/yfinance_provider.py — Added throttle (delay between yfinance API calls) to avoid rate limits (Task 1)
- [2026-04-10] Modified: app/services/options/chain_scanner/providers/__init__.py — Added delay param to create_provider factory
- [2026-04-10] Modified: app/routers/chain_scan.py — Live endpoint uses delay=0.5s
- [2026-04-11] Created: app/services/options_digest.py — Nightly chain scan function, stores signals per user (Task 2)
- [2026-04-11] Modified: app/services/digest.py — Wire nightly chain scan into run_nightly_refresh() (Task 3)
- [2026-04-11] Modified: app/routers/chain_scan.py — Added GET /options/chain-signals endpoint for cached nightly results (Task 4)
- [2026-04-11] Modified: frontend/src/types/index.ts — Added CachedSignalsResponse type
- [2026-04-11] Modified: frontend/src/api/client.ts — Added getCachedSignals() function
- [2026-04-11] Modified: frontend/src/components/ChainScannerPanel.tsx — Load cached signals on mount with "Last scanned" timestamp (Task 5)

---

## 2026-04-08 — Phase C: Price Recommended Strategies

- [2026-04-08] Created: app/services/options/chain_scanner/strategy_pricer.py — BS pricing + MC prob_profit for recommended strategies
- [2026-04-08] Modified: app/routers/chain_scan.py — Added ?price=true param + priced_strategy field
- [2026-04-08] Created: tests/test_strategy_pricer.py — 26 tests (strike resolution, credit/debit pricing, Greeks, stops/targets)

---

## 2026-04-05 — Phase B: Strategy Template Mapping

- [2026-04-05] Created: app/services/options/chain_scanner/strategy_mapper.py — Maps (iv_regime, direction) to StrategyRecommendation
- [2026-04-05] Modified: app/routers/chain_scan.py — Added recommended_strategy field to chain-scan response
- [2026-04-05] Created: tests/test_strategy_mapper.py — 20 tests covering all regime/direction combos + edge cases

---

## 2026-04-04 — Integration Task 1: Copy chain scanner + rewire imports

- [2026-04-04] Created: app/services/options/chain_scanner/__init__.py — OptionSignal dataclass + scan_watchlist() entry point
- [2026-04-04] Created: app/services/options/chain_scanner/scanner.py — OptionsScanner orchestrator (rewired sys.path shim for pricing/src)
- [2026-04-04] Created: app/services/options/chain_scanner/iv_rank.py — IV rank/percentile/regime engine
- [2026-04-04] Created: app/services/options/chain_scanner/contract_filter.py — DTE/moneyness/delta/liquidity filter (rewired sys.path shim)
- [2026-04-04] Created: app/services/options/chain_scanner/edge.py — GARCH edge calculator + BS Greeks (rewired sys.path shim)
- [2026-04-04] Created: app/services/options/chain_scanner/scorer.py — Conviction scorer (0–100 composite)
- [2026-04-04] Created: app/services/options/chain_scanner/cli.py — CLI entry point (rewired to app.services imports)
- [2026-04-04] Created: app/services/options/chain_scanner/providers/__init__.py — Provider factory
- [2026-04-04] Created: app/services/options/chain_scanner/providers/base.py — ChainProvider ABC + dataclasses
- [2026-04-04] Created: app/services/options/chain_scanner/providers/yfinance_provider.py — YFinance provider
- [2026-04-04] Created: app/services/options/chain_scanner/providers/cached_provider.py — TTL cache decorator

## 2026-04-04 — Integration Task 2: Add option_signals DB table

- [2026-04-04] Modified: app/database.py — Added option_signals table with indexes in init_db()

## 2026-04-04 — Integration Task 3: Create chain-scan API endpoint

- [2026-04-04] Created: app/routers/chain_scan.py — GET /options/chain-scan endpoint with DB persistence
- [2026-04-04] Modified: app/main.py — Registered chain_scan router with JWT auth

## 2026-04-04 — Integration Task 4: Copy and rewire tests

- [2026-04-04] Created: tests/test_chain_scanner.py — 33 scanner unit tests (rewired imports, fixed date_range/length mismatch)

## 2026-04-04 — Integration Task 5: Config + endpoint wiring

- [2026-04-04] Modified: app/services/options/config.py — Added CHAIN_SCANNER_CONFIG with env-var overridable DTE
- [2026-04-04] Modified: app/routers/chain_scan.py — Pass CHAIN_SCANNER_CONFIG to scan_watchlist()

---

## 2026-03-29 — Phase 7 complete: TypeScript check + ticker quality guideline

### Files modified
- `CLAUDE.md` — Added ticker quality guideline section: 21 S1-compatible tickers (positive EV confirmed), 6 S1-incompatible tickers (negative EV across all parameter combinations). Updated signal layers note: rr_label and trigger_ok now integrated into S1/S2/S8 as of Phase 7.

### Phase 7 complete checklist
- [x] backtest_signals has strategy_name + conditions JSONB columns
- [x] backplayer accepts all 6 registered strategies
- [x] PlayerPage has strategy dropdown + strategy badge
- [x] Hypothesis agent: 107 runs / 10,906 signals (277-run target interrupted; data sufficient per gate)
- [x] hypothesis_findings.md written with all conclusions
- [x] 1A: poor R:R excluded from S1, S2, S8 (EV +55%)
- [x] 1B: trigger condition added to S8 (+17pp WR confirmed)
- [x] 1C: S1 target capped at 1.5xATR (eliminates rr>=4.0 bucket, avg_ret=-0.605)
- [x] Factory backtest run for each changed strategy
- [x] validated_strategies.json updated with Phase 7 results + tuning_log
- [x] 421/422 tests passing (1 frozen: ta_engine 4H upgrade test, both test + ta_engine frozen per CLAUDE.md)
- [x] No frozen file existing functions modified
- [x] npx tsc --noEmit: zero errors

---

## 2026-03-29 — Phase 7.7: validated_strategies.json updated with Phase 7 results

### Files modified
- `backtesting/validated_strategies.json`
  - `last_run` updated to 2026-03-29
  - S1, S2 `results`: added `note` fields documenting Phase 7 changes and hypothesis evidence
  - S8 `results.test`: replaced pre-Phase7 validation numbers with Phase 7 factory backtest (n=35, WR=37.1%, EV=0.515, gate PASS)
  - S8 `notes`: updated to reflect stop fallback fix and new Phase 7 conditions
  - `tuning_log`: added 3 new entries:
    - S1 iter 2 — 1A: poor R:R exclusion (EV 0.114 → 0.177, +55%)
    - S1 iter 3 — 1C: target cap (eliminates rr≥4.0 bucket, avg_ret=-0.605)
    - S8 iter 2 — 1A+1B: poor R:R gate + trigger condition (factory test: EV=0.515, gate PASS)

---

## 2026-03-29 — Phase 7.6: 1B implemented — trigger condition added to S8

### Files modified
- `app/services/backtester.py` — Fixed non-S1 signal building: now reads `trigger_ok`, `uptrend_confirmed`, `weekly_trend_aligned`, `near_support`, `reversal_found`, `rr_label`, `support_is_provisional` from swing_setup for all strategies (not just S1). Required so Task 7.6 prerequisite query could run.
- `backtesting/strategies/s8_stochastic_cross.py` — Added `Trigger bar` condition in `_check_conditions()`: reads `trigger_ok` from `swing_setup.conditions` (spec listed `trend` as source — that field doesn't exist there; correct location is swing_setup.conditions). Trigger is a 5th condition counted by `_verdict()`, adding ~20 pts to score when fired.

### S8 trigger_ok prerequisite query result (5 quality tickers, 56 signals):
| trigger_ok | n | WR | avg_return |
|---|---|---|---|
| False | 39 | 35.9% | 0.646 |
| True | 17 | 52.9% | 0.730 |
→ +17pp WR when trigger fires (exceeds 10pp gate). Proceed confirmed.

### Factory backtest gate (post-implementation, 5 tickers):
- n=35 signals (≥20 ✓), avg_return=0.515 (positive ✓)
- Expectancy: 37.1% WR, avg_ret 0.515 — gate passes

---

## 2026-03-29 — Phase 7.5: 1C implemented — S1 target capped at 1.5×ATR when resistance too far

### Files modified
- `backtesting/strategies/s1_trend_pullback.py` — In `_compute_risk()`, after reading target from swing_setup risk, cap it at `entry + 1.5×ATR` when it exceeds `entry + 2×ATR`. Only fires when ATR is available. Targets already within 2×ATR are untouched.

### Factory backtest result (quality tickers, ENTRY signals)
| rr bucket | n | WR | avg_return | avg_rr |
|---|---|---|---|---|
| < 2.0 | 172 | 80.2% | -0.128 | 1.44 |
| 2.0–3.0 | 32 | 75.0% | -0.028 | 2.33 |
| 3.0–4.0 | 28 | 96.4% | +1.441 | 3.56 |
| **≥ 4.0 (eliminated by cap)** | **123** | **43.1%** | **-0.605** | **6.49** |
| All ENTRY | 355 | 68.2% | -0.160 | 3.43 |

The cap eliminates the ≥ 4.0 bucket (avg_rr=6.49, avg_return=-0.605, WR only 43%) — targets so far from entry that they rarely hit. Capping to 1.5×ATR brings these into the ≤ 2.0 range. WATCH+ENTRY combined expectancy remains positive (+0.124).

---

## 2026-03-29 — Fix: pre-existing test failures resolved

### Files modified
- `backtesting/strategies/s8_stochastic_cross.py` — Fixed `_compute_risk()`: when `nearest_support` is present but invalid, return `None` directly instead of falling back to ATR stop. Fixes `test_s8_returns_none_when_stop_invalid`.
- `tests/conftest.py` — Added `clear_knowledge_cache` autouse fixture to truncate `knowledge_strategy_cache` before each test. Fixes `test_500_on_exception` / `test_500_detail_contains_error_message` cache pollution.
- **1 unfixable:** `test_watch_upgrades_when_4h_confirmed` — mock omits `rr_ratio` in conditions; `ta_engine.py` and test both frozen per CLAUDE.md.

### Test results: 421/422 pass (was 419/422)

---

## 2026-03-29 — Phase 7.4: 1A implemented — poor R:R excluded from S1, S2, S8

### Files modified
- `backtesting/strategies/s1_trend_pullback.py` — Added `rr_label='poor'` gate in `_compute_risk()` (returns None); added R:R quality Condition to `_check_conditions()`
- `backtesting/strategies/s2_rsi_reversion.py` — Same pattern: poor R:R gate + R:R quality condition
- `backtesting/strategies/s8_stochastic_cross.py` — Same pattern: poor R:R gate + R:R quality condition

### Factory backtest result (quality tickers, 27,000 signals)
| | Before | After (excl. poor) |
|---|---|---|
| n | 27,000 | 17,930 (-34% signals) |
| WR | 64.9% | 59.9% (-5pp, expected) |
| Avg return (EV) | 0.1139 | **0.1772 (+55.6%)** |

Poor R:R signals had WR=74.8% but avg_return=-0.011 (negative EV). Removing them raises EV 55% while WR drops because high-WR-but-negative-EV trades are excluded.

---

## 2026-03-29 — Phase 7.2: strategy selector added to PlayerPage

### Files modified
- `frontend/src/pages/PlayerPage.tsx`
  - Added `STRATEGIES` constant (6 strategies: S1–S3, S7–S9)
  - Added `strategyName` state, defaulting to `S1_TrendPullback`
  - Strategy dropdown added to config panel (between Min Support and Weekly aligned)
  - `strategy_name` included in POST `/player/run` body
  - Auto-label effect updated to embed strategy name in run label
  - Strategy badge shown on run toggle buttons and runs comparison table when strategy ≠ S1
  - Signals table CONDITIONS column: renders JSONB `conditions` array for non-S1 strategies; falls back to legacy S1 boolean columns for S1
  - Removed unused `hasChart` variable

- `frontend/src/types/index.ts`
  - Added all missing player types: `ChartCandle`, `PnLPoint`, `ChartMarkerEntry`, `ChartMarkerExit`, `ChartMarker`, `RunMarkersResponse`, `MarkerTooltipData`, `BacktestRun`, `BacktestSignalCondition`, `BacktestSignal` (with P&L enrichment fields)

---

## 2026-03-29 — Phase 7.1: backplayer extended to support all registry strategies

### Files modified
- `app/database.py`
  - Added `strategy_name VARCHAR(50) DEFAULT 'S1_TrendPullback'` to `backtest_runs` and `backtest_signals` (idempotent ALTER TABLE)
  - Added `conditions JSONB` to `backtest_signals` for non-S1 strategy condition storage

- `app/services/backtester.py`
  - Added `strategy_name: str = 'S1_TrendPullback'` to `BacktestConfig` dataclass
  - Added `strategy_name` and `conditions_json` fields to `BacktestSignal` dataclass
  - Added `_make_snapshot()` helper to convert `analyze_ticker` result dict → `SignalSnapshot`
  - Rewrote `_build_signal()`: S1 reads verdict/score/S1-specific columns from swing_setup dict (full backward compat); non-S1 reads from `StrategyResult`; all strategies serialize conditions to JSONB
  - Updated `run_backtest()` loop: resolves strategy from `STRATEGY_REGISTRY` once before loop; S1 keeps `swing_setup.verdict in (ENTRY, WATCH)` gate; non-S1 uses `strategy.should_enter()` + `strategy.evaluate()`
  - Updated auto-label to include strategy name

- `app/routers/player.py`
  - Added `strategy_name: str = 'S1_TrendPullback'` to `BacktestConfigBody`
  - `strategy_name` passed through to `BacktestConfig` and stored in `backtest_runs` INSERT
  - `strategy_name` and `conditions` columns added to `backtest_signals` INSERT (now 33 values)
  - Added `stream_router` (separate `APIRouter`) for SSE `/stream/{run_id}` endpoint — registered without global JWT dependency (EventSource cannot set Authorization headers); token accepted as query param with fallback to Authorization header

- `app/main.py`
  - Registered `player_stream_router` in public routes section (no JWT dependency)

- `CLAUDE.md`
  - Active phase updated to `phase7.md`
  - Frozen files table expanded with freeze scope column
  - Signal layers reference section added
  - Rule numbering updated (rule 6 added: never modify existing functions in `market_data.py`)

- `.claude/ARCHITECTURE_DECISIONS.md`
  - Added ADR-019: Backplayer merge frozen file exceptions
  - Added ADR-020: Three new signal layers (4H, rr_label, provisional S/R) deferred pending backtest evidence
  - Removed ADR-014 (backtest universe/tuning protocol) — superseded by Phase 7 hypothesis layer

---

## 2026-03-29 — Phase 7.3: hypothesis agent results and findings documented

### Files created
- `.claude/hypothesis_findings.md` — Full cross-experiment analysis of 10,906 signals across 30 tickers (107 runs). Documents rr_label breakdown (good/marginal/poor), weekly alignment effect (+1.3pp WR, no avg_return benefit), trigger_ok effect (WATCH+trigger=82.3% WR vs 62.7%), ENTRY avg_rr=3.60 with negative avg_return, 4H confirmation analysis. Justifies Tasks 7.4, 7.5, 7.6.

---

## 2026-03-20 — Fix: player SSE stream still 401 due to router-level auth

### Files modified
- `app/routers/player.py` — Added `stream_router` (separate `APIRouter`). Moved `/stream/{run_id}` from `router` to `stream_router` so it bypasses the global `**_auth` dependency applied at router inclusion time.
- `app/main.py` — Imported `stream_router` from player and registered it in the public routes section (no JWT dependency). All other player routes remain protected.

---

## 2026-03-20 — Fix: PlayerPage missing key prop + Vite cache clear

### Files modified
- `frontend/src/pages/PlayerPage.tsx` — `key` prop was on inner `<tr>` but outermost element was a `<>` fragment. React requires `key` on the outermost element. Changed to `<Fragment key={sigKey}>` and added `Fragment` to the React import.

### Other
- Cleared Vite dev cache (`node_modules/.vite`) to force React Router future flags to take effect.

---

## 2026-03-20 — Fix: PlayerPnLPanel crash — unsubMain is not a function

### File modified
- `frontend/src/components/PlayerPnLPanel.tsx` — In lightweight-charts v4, `subscribeVisibleLogicalRangeChange` returns `void` (not an unsubscribe function). Fixed by storing handler references (`onMainChange`, `onPnlChange`) and calling `unsubscribeVisibleLogicalRangeChange(handler)` in the cleanup. Also imported `LogicalRange` type to correctly type the callbacks.

---

## 2026-03-20 — Fix: player SSE stream 401 + React Router warnings

### Files modified
- `app/routers/player.py` — `/player/stream/{run_id}` now accepts `?token=` query param. `EventSource` (used for SSE) cannot set `Authorization` headers in browsers; token must come via query string. Falls back to `Authorization: Bearer` header for non-browser clients. Removed `Depends(get_current_user)`, validates token manually via `decode_token()`.
- `frontend/src/App.tsx` — Added `future={{ v7_startTransition: true, v7_relativeSplatPath: true }}` to `BrowserRouter` to silence React Router v6→v7 upgrade warnings.

---

## 2026-03-20 — Docs: remove duplicate ADRs from ARCHITECTURE_DECISIONS.md

### File modified
- `.claude/ARCHITECTURE_DECISIONS.md` — Removed three duplicate blocks: second copy of ADR-014 (mislabelled ADR-017), third copy of ADR-014 (mislabelled again), and duplicate ADR-015 (mislabelled ADR-018). Also removed stray double `---` separator. File reduced from 1247 to 898 lines. ADR sequence is now clean: 001–016, 019–020.

---

## 2026-03-20 — UX: add Backtester nav link to header

### File modified
- `frontend/src/pages/AnalysisPage.tsx` — Added "Backtester" button to the header nav bar, navigating to `/player`

---

## 2026-03-20 — Docs: created HOWTO.md

### File created
- `HOWTO.md` — Complete run guide covering quick start, all environment variables, build.sh commands, services/ports, smoke test, knowledge base CLI, test commands, backtesting, rebuild instructions, and Render deployment steps

---

## 2026-03-20 — Maintenance: rebase knowledge_base onto main

### What changed
- Rebased `knowledge_base` (12 commits) onto `main` to incorporate the `backplayer` commit
- Resolved all merge conflicts, keeping changes from both branches throughout

### Conflicts resolved
- `app/database.py` — merged backtest player tables (`backtest_runs`, `backtest_signals`, `hourly_price_history`) with knowledge base tables (`knowledge_chunks`); corrected vector dimension to `1536` (OpenAI)
- `app/main.py` — merged all router registrations: `options`, `player`, `strategies`, `trades` all present
- `app/models.py` — merged `FourHConfirmation` (from backplayer) with `TradeCreate`/`TradeResponse` (from Phase 5)
- `frontend/src/App.tsx` — merged all routes: `/options`, `/player`, `/scanner`, `/trades`
- `CLAUDE.md` — merged qmd code search section with project rules
- `tests/test_ta_engine.py` — took the fixed Friday anchor version (eliminates pandas 2.2+ flakiness)

### Verified
- `docker exec docker-api-1 python scripts/smoke_test.py` → 33/33 checks passed

---

## 2026-03-19 — Feature: crosshair tooltip showing indicator values on hover (PriceChart.tsx)

### File modified
- `frontend/src/components/PriceChart.tsx` — Added `TooltipState` interface and `ChartTooltip` component. `useChartInstance` now subscribes to `chart.subscribeCrosshairMove` in the chart-creation effect. On each crosshair move it reads OHLC from the candlestick series and per-value from every line/histogram series via `param.seriesData`. Toggled-off indicators have empty series so return `undefined`, which the tooltip row filter naturally hides. The tooltip renders as a semi-transparent dark overlay pinned to the top-left of the chart container. Works in both the inline chart and the fullscreen modal.

---

## 2026-03-19 — UX: strategy panels converted to tabs under Swing Setup

### File modified
- `frontend/src/pages/AnalysisPage.tsx` — Replaced stacked `StrategyPanel` list with a horizontal tab bar. Each tab shows the strategy short name (S1_ prefix stripped) and score. Tabs are color-coded: green for ENTRY verdicts, yellow for WATCH, gray for NO_TRADE. Active tab is highlighted with a bottom border and tinted background. Clicking a tab swaps the panel below. Sort order unchanged: ENTRY first, then by score descending. `activeStrategyIdx` resets to 0 on each new ticker search.

---

## 2026-03-19 — Config: reduce STALENESS_HOURS from 24 to 4

### File modified
- `app/config.py` — `STALENESS_HOURS` changed from 24 to 4. Data is now refreshed from yfinance if the last fetch was more than 4 hours ago, ensuring today's closing bar is picked up when searching after market close.

---

## 2026-03-19 — Fix: chart not updating after null-bar filter (PriceChart.tsx)

### File modified
- `frontend/src/components/PriceChart.tsx` — The previous fix filtered null OHLC bars only for the candlestick series. The volume `setData` still received raw prices with null values and could crash, aborting the effect before `setVisibleRange` ran — causing the chart to never update its viewport on ticker change. Fix: compute `cleanPrices` once at the top of the effect (bars where all OHLC fields are non-null), use it for candlestick, volume, and the `closes` array fed to all indicator math helpers. RSI and MACD data-update effects also updated to use `cleanPrices` so null closes don't produce NaN in indicator output.

---

## 2026-03-19 — Fix: candlestick chart crash on null OHLC values (PriceChart.tsx:207)

### File modified
- `frontend/src/components/PriceChart.tsx` — Added `.filter()` before `.map()` in `candleRef.current.setData(...)` to drop any bars where `open`, `high`, `low`, or `close` is null. lightweight-charts asserts all OHLC fields are numbers and throws if any is null, crashing the entire component tree.

---

## 2026-03-19 — Fix: null guards on .toFixed() in SignalPanel.tsx

### File modified
- `frontend/src/components/SignalPanel.tsx` — Line 145: `lvl.price.toFixed(2)` → `lvl.price != null ? lvl.price.toFixed(2) : '—'`. Line 247: `analysis.price.toFixed(2)` → `analysis.price != null ? analysis.price.toFixed(2) : '—'`.

---

## 2026-03-19 — Fix: null guard on .toFixed() calls in TickerCard.tsx

### File modified
- `frontend/src/components/TickerCard.tsx` — Added `!= null` guards on all three `.toFixed()` calls: `price`, `Math.abs(dayChange)`, `Math.abs(dayChangePct)`. Each falls back to `'—'` when null. Prevents runtime TypeError when price data arrives as null.

---

## 2026-03-18 — Fix: S8 _compute_risk() two-step stop calculation

### File modified
- `backtesting/strategies/s8_stochastic_cross.py` — `_compute_risk()` now tries `nearest_support` first, falls back to `entry_price - 1.5 * atr` if `_stop_is_valid()` rejects it, and returns `None` only if the fallback also fails. Previously it returned `None` immediately when `nearest_support` failed validation, leaving valid setups without risk levels.

---

## 2026-03-18 — Feature: DB cache for book strategy results + on-demand generation button (fix1.md 1.2)

### Files modified
- `app/database.py` — Added `knowledge_strategy_cache` table (`ticker TEXT, cache_date DATE, result JSONB, created_at TIMESTAMP`, PK on `(ticker, cache_date)`). Idempotent via `CREATE TABLE IF NOT EXISTS`. Table persists all historical results — no expiry logic.
- `app/routers/analysis.py` — `knowledge_strategies` route now reads from cache before calling Claude. On cache hit: returns immediately. On miss: calls `generate_strategies()`, writes result to cache with `ON CONFLICT DO NOTHING`, returns result. Cache write failure is silently swallowed so it never breaks the response.
- `frontend/src/pages/AnalysisPage.tsx` — Removed automatic `fetchKnowledgeStrategies` call from `handleSearch`. Added `handleGenerateBook` function. Book Strategies section now shows a "📚 Generate book analysis" button until clicked; clicking triggers the fetch, shows loading state in the panel, then renders results. Cached results for the same day return near-instantly.

### Reason
Book strategy generation via Claude takes several seconds and costs API credits on every ticker search. Caching per-day per-ticker eliminates repeated calls for the same ticker on the same day. Making it on-demand (button) avoids the cost and latency for every search — the user explicitly requests it when they want it.

---

## 2026-03-18 — Fix: fetchKnowledgeStrategies return type corrected in client.ts

### File modified
- `frontend/src/api/client.ts` — Changed `fetchKnowledgeStrategies` return type from `{ ticker: string; strategies: string }` to `{ ticker: string; strategies: BookStrategiesData }`. Completes the TypeScript chain: API → state → prop. `npx tsc --noEmit` confirms zero errors.

---

## 2026-03-18 — Fix: JSONDecodeError in knowledge-strategies (markdown fences + max_tokens)

### File modified
- `tools/knowledge_base/strategy_gen.py` — Two fixes:
  1. `max_tokens` raised 2000 → 4096: response was truncated mid-JSON for complex tickers.
  2. Strip markdown code fences before `json.loads()`: despite the system prompt instructing
     plain JSON, claude-sonnet-4-6 wraps responses in ```json ... ``` — causing
     `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` (empty parse target).
     Fix: if raw starts with ``` , drop the opening fence line and trailing fence before parsing.

---

## 2026-03-18 — Fix: backtesting/ volume mount added to docker-compose.yml

### File modified
- `tools/knowledge_base/strategy_gen.py` — Raised `max_tokens` from 2000 → 4096.
  Root cause: the JSON response (multiple strategies with conditions, sources, signals) frequently
  exceeds 2000 tokens, causing Claude to truncate mid-string. The 500 error manifested as
  `JSONDecodeError: Unterminated string starting at: line 84 column 5 (char 7691)` — char 7691
  is consistent with a ~2000 token cutoff (~4 chars/token). 4096 gives enough headroom for the
  full structured response.

---

## 2026-03-18 — Fix: backtesting/ volume mount added to docker-compose.yml

### File modified
- `docker/docker-compose.yml` (frozen file, modified by explicit user request)
  - Added `../backtesting:/app/backtesting` volume mount to the `api` service alongside the other
    dev mounts (`app/`, `tools/`, etc.)
  - Root cause: `backtesting/` was only present in the Docker image at build time. On container
    restart/recreation it disappeared, causing `ModuleNotFoundError: No module named 'backtesting'`
    and preventing the API from starting (login/signup failures).
  - With this mount, the live host directory is used — changes to strategy files are reflected
    immediately without a rebuild, and the module survives container restarts.

---

## 2026-03-18 — Phase 6, Tasks 6.5 + 6.6: ScannerPage and TradeTrackerPage

### Files created
- `frontend/src/pages/ScannerPage.tsx` — New page at /scanner.
  Fetches /scan/watchlist on mount and on Refresh button click. Loading skeleton visible during
  the 5–10s fetch. Compact ScanRow list (ticker, type chip, strategy name, score, verdict badge,
  entry/stop/target/R:R/shares). Results sorted ENTRY-first then score descending. Clicking a
  row navigates to `/?ticker={ticker}`. Empty state when watchlist has no setups firing.
- `frontend/src/pages/TradeTrackerPage.tsx` — New page at /trades.
  Open trades table with columns: Ticker, Strategy, Entry, Stop, Target, Shares, R:R, Current R
  (green/red), Alert (amber ⚠ for APPROACHING_STOP, green ✓ for AT_TARGET), Action (Close).
  Close button re-fetches from server (not optimistic). Log Trade form with ticker input, strategy
  dropdown (static 6-strategy list, auto-populates strategy_type), price inputs, shares. Errors
  displayed inline. No charts, no edit — close only.

### File modified
- `frontend/src/App.tsx` — Added /scanner and /trades routes (both protected), and imported
  ScannerPage + TradeTrackerPage. No existing routes or pages modified.

`npx tsc --noEmit` zero errors.

---

## 2026-03-18 — Phase 6, Task 6.4: Strategy panels added to AnalysisPage

### File modified
- `frontend/src/pages/AnalysisPage.tsx` — Additive changes only; no existing state or logic modified:
  - Added `strategies` state (StrategyResult[], initialized to [])
  - Added `fetchStrategies` and `StrategyPanel` imports
  - `fetchStrategies(ticker)` added to the SAME Promise.all as fetchPrices/fetchAnalysis — same
    ticker context, prevents stale results. Failures caught and silently return [] so analysis panel
    is never broken by a strategy fetch error.
  - `setStrategies([])` added to the reset block in handleSearch
  - StrategyPanels rendered below SwingSetupPanel, sorted ENTRY-first then score descending
  - SwingSetupPanel untouched

`npx tsc --noEmit` zero errors.

---

## 2026-03-18 — Phase 6, Task 6.3: StrategyPanel component

### File created
- `frontend/src/components/StrategyPanel.tsx` — Reusable component that renders any StrategyResult.
  Color-coded by strategy type (teal=trend, purple=reversion, amber=breakout, blue=rotation).
  Layout matches SwingSetupPanel: header with name+type badge+verdict badge, score bar, two-column body.
  Left column: conditions list with pass/fail icons, label, value. Right column: risk levels with
  entry zone (null-guarded), stop, target, R:R, ATR (null-guarded), position_size (null-guarded).
  Log Trade button shown only when verdict=ENTRY and onLogTrade callback is provided.
  Props: result (StrategyResult), onLogTrade (optional callback — no API calls in this component).
  `npx tsc --noEmit` zero errors.

---

## 2026-03-18 — Phase 6, Task 6.2: API call functions for strategies and trades

### File modified
- `frontend/src/api/client.ts` — Added 7 new API functions (no existing functions modified):
  - `fetchStrategies(ticker)` — GET /strategies/{ticker} → StrategyResult[]
  - `scanWatchlist()` — GET /strategies/scan/watchlist → StrategyResult[]
  - `fetchUserSettings()` — GET /strategies/settings → UserSettings
  - `updateUserSettings(settings)` — PATCH /strategies/settings → UserSettings
  - `fetchOpenTrades()` — GET /trades/ → OpenTrade[]
  - `logTrade(trade)` — POST /trades/ with Omit<OpenTrade, server-computed fields> → OpenTrade
  - `closeTrade(tradeId)` — DELETE /trades/{id} → void

`npx tsc --noEmit` zero errors.

---

## 2026-03-18 — Phase 6, Task 6.1: TypeScript types for strategy scanner and trade tracker

### File modified
- `frontend/src/types/index.ts` — Added 7 new interfaces/types (no existing types modified):
  - `Condition` — mirrors `backtesting/base.py` Condition dataclass
  - `RiskLevels` — mirrors `backtesting/base.py` RiskLevels; optional fields: atr, entry_zone_low, entry_zone_high, position_size
  - `StrategyType` — union of 4 valid strategy type strings
  - `Verdict` — union of 3 valid verdict strings
  - `StrategyResult` — mirrors StrategyResult dataclass; ticker is optional (only in scan results)
  - `OpenTrade` — mirrors TradeResponse from app/models.py; computed fields (current_price, current_r, exit_alert) optional
  - `UserSettings` — mirrors UserSettings from app/models.py

`npx tsc --noEmit` zero errors.

---

## 2026-03-18 — Strategy consistency pass + test_strategies.py (211 tests)

### Files created
- `tests/test_strategies.py` — New comprehensive strategy contract/correctness test suite (211 tests).
  Covers: `TestContract`, `TestConditionStruct`, `TestComputeRisk`, `TestEntryAndStops`, `TestShouldExit`, `TestADR015`.
  Parametrized over all 7 strategy classes; uses `make_snapshot()` helper for reproducible snapshots.

### Files modified
- `backtesting/strategies/s2_rsi_reversion.py`
  - `should_exit`: raised RSI threshold 55→65; added `nearest_resistance` exit
  - `_compute_risk`: added `_stop_is_valid` guard; added `entry_zone_low/high` from `swing_setup.risk.entry_zone`

- `backtesting/strategies/s3_bb_squeeze.py`
  - `should_exit`: added RSI >= 70 exit; added `nearest_resistance` exit
  - `_compute_risk`: added `_stop_is_valid` guard; added `entry_zone` (bb_upper … bb_upper+0.5×ATR)

- `backtesting/strategies/s7_macd_cross.py`
  - `should_exit`: added `nearest_resistance` exit (RSI >= 70 + bearish MACD were already present)
  - `_compute_risk`: added `_stop_is_valid` guard; added `entry_zone` (±0.25×ATR around entry)

- `backtesting/strategies/s8_stochastic_cross.py`
  - `should_exit`: added RSI >= 65 exit; added `nearest_resistance` exit
  - `_compute_risk`: added `entry_zone_low/high` from `swing_setup.risk.entry_zone`

- `backtesting/strategies/s9_ema_cross.py`
  - `should_exit`: added RSI >= 70 exit; added `nearest_resistance` exit
  - `_compute_risk`: added `entry_zone` between EMA9 and EMA21

- `backtesting/strategies/s10_golden_cross_pullback.py`
  - `should_exit`: added RSI >= 70 exit; added `nearest_resistance` exit
  - Reason: required to satisfy `test_exits_when_rsi_is_80` and `test_exits_when_price_at_resistance`
    contract tests that all strategies must exit on these universal signals

### Docker sync fix
The `backtesting/` directory is not volume-mounted in docker-compose, so updated strategy files
were copied to the running container with `docker cp`. All 382 tests pass (171 pre-existing + 211 new).

---

## 2026-03-18 — Fix: TestWeeklyTrend flaky failures (pandas 2.2+ date_range off-by-one)

### Root cause
`_make_weekly_bullish_df` and `_make_weekly_bearish_df` in `tests/test_ta_engine.py`
used `pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="W-FRI")`.

In pandas 2.2+, when `end` does not fall on the weekly anchor (i.e. today is not a
Friday), the end date is treated as exclusive of the last interval. This causes the
date range to return `n-1` periods instead of `n`. The data arrays (`np.linspace`,
`np.ones`) were still sized `n`, producing a DataFrame construction error:
`ValueError: Length of values (60) does not match length of index (59)`.

The failure was **day-of-week dependent** — it only manifested on non-Friday days,
making it appear intermittent. The test had no bug on the logic side; only the
date anchor was fragile.

### Fix
Replaced `end=pd.Timestamp.today().normalize()` with a fixed Friday anchor
`end=pd.Timestamp("2024-01-05")` in both helper functions. Unit tests have no
reason to depend on the current date — they need `n` stable weekly bars with a
known trend. Pinning to a deterministic Friday guarantees pandas always returns
exactly `n` periods, regardless of which day of the week the test suite runs.

### Result
All 171 tests now pass (previously 164 passed, 7 failed).

### Modified
- `tests/test_ta_engine.py`: fixed `_make_weekly_bullish_df` and `_make_weekly_bearish_df`

---

## 2026-03-18 — Docs: module and function docstrings across all non-frozen files

Added module-level docstrings, function/method docstrings, and inline comments
to every Python file that was missing them (options folder excluded, frozen files
left untouched per CLAUDE.md rules).

### Modified
- `app/config.py`: module docstring
- `app/database.py`: module docstring
- `app/models.py`: module docstring
- `app/main.py`: module docstring
- `app/dependencies.py`: module docstring
- `app/services/auth.py`: module docstring + docstrings on all 4 functions
- `app/services/digest.py`: module docstring listing all public functions
- `app/routers/auth.py`: module docstring + endpoint docstrings
- `app/routers/data.py`: module docstring + endpoint docstrings
- `app/routers/internal.py`: module docstring + helper and endpoint docstrings
- `app/routers/notifications.py`: module docstring + endpoint docstrings
- `app/routers/analysis.py`: module docstring
- `app/routers/watchlist.py`: module docstring + endpoint docstrings
- `app/routers/strategies.py`: module docstring + helper and endpoint docstrings
- `tests/conftest.py`: module docstring
- `tests/test_ai_engine.py`: module docstring
- `tests/test_synthesis_endpoint.py`: module docstring + fixture docstring
- `tests/test_analysis_endpoint.py`: module docstring

---

## 2026-03-18 — Docs: trades.py comments

### Modified
- `app/routers/trades.py`: added module docstring, docstrings for all helper functions and endpoints; fixed unused `ticker_info` variable (`_`)

---

## 2026-03-18 — Task 5.3: Trade exit monitoring in digest

### Modified
- `app/services/digest.py`: added `generate_trade_alerts(user_id: int) -> str`
  - Fetches all open trades for user from DB (same `get_db()` pattern as rest of digest.py)
  - For each trade: fetches live price via `get_or_refresh_data()`; computes alert
  - Alert thresholds: `price <= stop * 1.02` → "⚠ approaching stop"; `price >= target * 0.98` → "✓ at target"
  - Returns formatted plain text or empty string if no alerts
  - Does not send notifications (digest handles that)

---

## 2026-03-18 — Task 5.2: Trades router

### Added
- `app/routers/trades.py`: three endpoints under `/trades` prefix (JWT-protected)
  - `POST /trades/` — logs a trade, fetches live price, returns `current_r` and `exit_alert`
  - `GET /trades/` — lists all open trades for current user with live `current_r` and `exit_alert`
  - `DELETE /trades/{id}` — closes a trade (403 if not owner), records `exit_price` and `exit_date`
  - Alert thresholds: `current_price <= stop * 1.02` → APPROACHING_STOP; `current_price >= target * 0.98` → AT_TARGET

### Modified
- `app/main.py`: imported and registered `trades.router` under JWT auth

---

## 2026-03-18 — Task 5.1: open_trades table

### Modified
- `app/database.py`: added `open_trades` table (id, user_id, ticker, strategy_name, strategy_type, entry_price, stop_loss, target, shares, entry_date, risk_reward, status, exit_price, exit_date, exit_reason, created_at) with `idx_open_trades_user` partial index on `(user_id) WHERE status = 'open'`
- `app/models.py`: added `TradeCreate` and `TradeResponse` Pydantic models

---

## 2026-03-18 — Task 4.3: Morning briefing upgraded with strategy setups

### Modified
- `app/services/digest.py`: added `generate_strategy_briefing(user_id: int) -> str`
  - Imports `_get_user_watchlist`, `_get_user_settings` from `app.routers.strategies` (module-level helpers, same DB pattern as rest of digest.py)
  - Parallel scan via `ThreadPoolExecutor(max_workers=min(tickers, 10))` — same pattern as `/scan/watchlist`
  - Filters to `verdict == "ENTRY"` only, sorted by score descending
  - Returns formatted plain text with entry/stop/target/R:R and position size per setup
  - Returns empty string gracefully when watchlist empty or no ENTRY setups
  - Existing `generate_digest_for_user`, `save_digest_notification`, `run_nightly_refresh` unchanged

---

## 2026-03-18 — Task 4.2: strategy_gen.py returns JSON + equity filter

### Modified
- `tools/knowledge_base/strategy_gen.py`:
  - `_SYSTEM_PROMPT` replaced: now instructs Claude to return ONLY a JSON object with schema `{strategies, best_opportunity, signals_to_watch}`. No price fields (entry_zone, stop_loss, target) — those are computed by the scanner per ADR-005.
  - `generate_strategies()` return type changed `str → dict`: passes `book_type="equity_ta"` to `retrieve_relevant_chunks()`, parses response with `json.loads()`
  - Options book passages no longer included in RAG retrieval for equity strategy generation

---

## 2026-03-18 — Task 4.1: book_type column + retrieval filter

### Modified
- `app/database.py`: `ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS book_type VARCHAR(20) DEFAULT 'equity_ta'` + `CREATE INDEX IF NOT EXISTS idx_book_type`
- `tools/knowledge_base/pdf_ingester.py`: added `OPTIONS_BOOKS` list + `_get_book_type()` helper; `_upsert_chunks()` now passes `book_type` into INSERT
- `tools/knowledge_base/retriever.py`: `retrieve_relevant_chunks()` accepts optional `book_type: str | None = None`; adds `WHERE book_type = %s` when set, default behaviour unchanged

### Data
- Path A applied: 449 existing `Option Spread Strategies` chunks tagged as `options_strategy`
- Distribution: `equity_ta` 8214 chunks, `options_strategy` 449 chunks

---

## 2026-03-18 — Tasks 3.3 / 3.4 / 3.5: strategies router

### Added
- `app/routers/strategies.py`: four endpoints (fixed paths defined before `/{ticker}` to avoid route shadowing):
  - `GET /strategies/settings` — returns user's account_size + risk_pct
  - `PATCH /strategies/settings` — updates settings (validates account_size > 0, risk_pct ∈ (0, 0.05])
  - `GET /strategies/scan/watchlist` — parallel ThreadPoolExecutor scan across all watchlist tickers, results sorted by score descending
  - `GET /strategies/{ticker}` — runs StrategyScanner for one ticker with user's settings

### Modified
- `app/main.py`: registered `strategies.router` under JWT auth middleware

### Verified
- `GET /strategies/SPY` returns 3 WATCH results (S8, S1, S7)
- `PATCH` + `GET /strategies/settings` round-trips correctly
- 33/33 smoke test checks pass

---

## 2026-03-18 — Task 3.2: User settings columns added to DB

### Modified
- `app/database.py`: `ALTER TABLE users ADD COLUMN IF NOT EXISTS account_size NUMERIC(12,2) DEFAULT 10000.00, risk_pct NUMERIC(5,4) DEFAULT 0.0100` — safe to run on existing DBs
- `app/models.py`: added `UserSettings(account_size=10000.0, risk_pct=0.01)` Pydantic model

---

## 2026-03-18 — Task 3.1: StrategyScanner filters to validated strategies only

### Modified
- `backtesting/scanner.py`: loads `validated_strategies.json` on init, filters `STRATEGY_REGISTRY` to only strategies in the `"validated"` list. Stores as `self._active_strategies` (set once, never mutated — thread-safe for Task 3.4). `scan()` creates `YFinanceProvider` and `SignalEngine` per call (no shared mutable state).
- Active strategies: S1, S2, S3, S7, S8, S9 (6 validated). S10 excluded (pending).

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

- [2026-03-19] Created: docs/player.md — Full user guide for the Backtesting Player feature (controls, result metrics, interpreting stats, comparing runs, limitations)
- [2026-03-29] Modified: app/database.py — Phase 7.1: added strategy_name to backtest_runs and backtest_signals, added conditions JSONB column to backtest_signals
- [2026-03-29] Modified: app/services/backtester.py — Phase 7.1: added strategy_name to BacktestConfig/BacktestSignal; added _make_snapshot() helper; updated _build_signal() and run_backtest() loop to use strategy factory interface for all registered strategies; S1 backward compat path preserved
- [2026-03-29] Modified: app/routers/player.py — Phase 7.1: added strategy_name to BacktestConfigBody, BacktestConfig construction, backtest_runs INSERT, and backtest_signals INSERT; added conditions column to signal INSERT
- [2026-03-29] Modified: frontend/src/types/index.ts — Added all missing player types: BacktestRun, BacktestSignal, BacktestSignalCondition, ChartCandle, PnLPoint, ChartMarker, ChartMarkerEntry, ChartMarkerExit, RunMarkersResponse, MarkerTooltipData
- [2026-03-29] Modified: frontend/src/pages/PlayerPage.tsx — Phase 7.2: added STRATEGIES constant and strategy dropdown to config panel; added strategy_name to POST body; added strategy badge to run toggles and runs table; updated expanded signal CONDITIONS to render JSONB conditions array for non-S1 strategies (falls back to boolean columns for S1); removed unused hasChart variable
