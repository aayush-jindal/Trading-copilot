# Architecture Decision Record — Trading Copilot

This document records every significant architectural decision made during
the design of Trading Copilot. For each decision: what was decided, why,
what was considered and rejected, and what constraints shaped the choice.

Do not delete entries. If a decision is reversed, add a new entry
explaining why. This file is the institutional memory of the project.

---

## ADR-001 — Application objective: decision support, not automation

**Date:** March 2026  
**Status:** Active

### Decision
The application is a personal decision support tool. It surfaces validated
signals and tells you when to enter and exit. You execute the trades yourself.
It does not execute trades automatically.

### Why
Automated execution requires broker API integration, order management, risk
circuit breakers, and regulatory considerations that are out of scope for
a personal tool. The primary value is in the signal quality and presentation,
not the execution layer. Human judgment remains in the loop for every trade.

### Rejected alternatives
- **Full automation via Alpaca API** — considered, deferred. Would require
  position management, order routing, fill handling, and a much more robust
  risk management layer. Can be added later if paper trading validates the system.

### Constraints
- Personal use, single user initially
- No broker integration in scope for phases 1-6

---

## ADR-002 — Two independent scoring systems, never merged

**Date:** March 2026  
**Status:** Active

### Decision
The equity swing setup scorer (`compute_swing_setup_pullback()` in
`ta_engine.py`) and the options bias scorer (`detect_bias()` in
`bias_detector.py`) are independent systems that must never be merged,
modified by Claude Code, or used interchangeably.

### Why
Each was designed for a specific purpose with specific weights calibrated
to its domain. The swing setup scorer produces a 0–100 score and
ENTRY/WATCH/NO_TRADE verdict for equity swing trades. The options bias
scorer produces a net integer and BULLISH/BEARISH/NEUTRAL label for
options strategy direction. Merging them would produce a meaningless hybrid.

The weights in both files encode domain knowledge that has not been
systematically backtested — they represent the best available prior.
Modifying them based on LLM judgment rather than backtested evidence
would be strictly worse.

### Rule derived from this decision
Both files are permanently frozen in `CLAUDE.md`. Claude Code may read
them to understand signal shapes. It may never edit them. Any future
weight changes must be driven by backtest evidence and made by a human.

### Rejected alternatives
- **Single unified scorer** — rejected. Options and equity have different
  signal vocabularies, different timeframes, and different risk profiles.
  A unified score would require arbitrary cross-domain weighting.

---

## ADR-003 — Strategy factory pattern

**Date:** March 2026  
**Status:** Active

### Decision
Every strategy implements exactly two methods: `_check_conditions()` and
`_compute_risk()`. Adding a strategy = one new file + one line in
`registry.py`. Nothing else changes anywhere.

### Why
The alternative was bespoke strategy classes with different interfaces.
That approach requires touching the scanner, the API router, and the
frontend component every time a new strategy is added. The factory pattern
decouples strategy logic from everything that consumes it.

The `SwingSetupPanel.tsx` component in the existing frontend proved the
pattern works — it shows conditions, risk levels, and a verdict. Every
new strategy panel is the same component with different data.

### Consequence
`StrategyResult` is the universal contract. Scanner, API, and frontend
all speak `StrategyResult`. They never know which strategy produced it.

### Rejected alternatives
- **Plugin system / dynamic loading** — over-engineered for this scale.
  A static registry list is simpler, explicit, and version-controlled.
- **Database-driven strategy configuration** — rejected. Strategy logic
  is code, not configuration. Storing it in a DB would make it untestable
  and unversionable.

---

## ADR-004 — Backtest gate before any strategy goes live

**Date:** March 2026  
**Status:** Active

### Decision
No strategy appears in the live scanner until it passes:
`total_trades >= 30 AND expectancy > 0` on the defined universe and
window (2019–2024 daily data). Results recorded in `validated_strategies.json`.

### Why
The alternative is running unvalidated strategies in the live scanner,
which would produce signals with unknown win rates. A signal with 40%
win rate and -0.3R expectancy is actively harmful — it loses money
consistently. The gate exists to ensure every signal presented to the
user has demonstrable historical edge.

30 trades is the minimum for statistical meaning. Fewer than 30 occurrences
means the win rate estimate has too wide a confidence interval to be useful.

### What the gate does NOT guarantee
- Future performance equal to backtest performance
- That market regime won't change
- That the strategy won't degrade over time

### Rule derived from this decision
`validated_strategies.json` is the bridge between backtest and live.
The scanner loads only strategies listed in `"validated"`. Moving a
strategy from `"pending"` to `"validated"` in that file is the only
deployment action needed — no code changes.

### Rejected alternatives
- **No gate, rely on live paper trading** — rejected. Paper trading takes
  60+ days to accumulate meaningful data. The backtest gives 5 years of
  data in minutes. Both are needed — backtest validates edge exists,
  paper trading validates it translates to live conditions.

---

## ADR-005 — RAG is an explainer, not a decision-maker

**Date:** March 2026  
**Status:** Active

### Decision
The RAG pipeline (book passages → Claude → narrative) explains why a
setup is valid. It never decides whether a setup is valid. The conviction
scorer decides. RAG fires only when scorer reaches ALERT/ENTRY threshold.

### Why
RAG retrieves passages from books and synthesizes them into explanations.
The quality of the explanation depends on retrieval quality, passage
relevance, and Claude's synthesis — none of which are quantitatively
validated against trading outcomes. Letting RAG decide entries would mean
trading based on unvalidated book passages without knowing their win rate.

The backtest-validated scorer has a known win rate. RAG provides the
qualitative rationale for a quantitatively validated signal. That is
the correct division of labor.

### Consequence
If the scorer says NO_TRADE, RAG does not fire regardless of what the
books say. The scorer is ground truth. RAG is color commentary.

### Rejected alternatives
- **RAG as primary signal source** — the initial implementation before
  this design was formalized. Produced good-looking output but with no
  statistical basis for the entry recommendations.
- **RAG disabled entirely** — rejected. The qualitative explanation adds
  genuine value for understanding why a setup makes sense. It also grounds
  the analysis in published technical analysis literature rather than
  black-box scoring.

---

## ADR-006 — Book type split: equity_ta vs options_strategy

**Date:** March 2026  
**Status:** Active

### Decision
Knowledge base chunks are tagged `book_type = 'equity_ta'` or
`book_type = 'options_strategy'` at ingestion time. Equity RAG queries
filter to equity books. Options RAG queries filter to options books.

### Why
The knowledge base contains 11 books: 9 on technical analysis of equities,
2 on options pricing and strategy. Without filtering, an equity strategy
query could retrieve passages about options pricing that are semantically
similar but contextually irrelevant. This produces confusing citations.

### Book classification
Equity TA (9): Technical Analysis of Stock Trends, Technical Analysis
Complete Resource, New Frontiers in Technical Analysis, Evidence-Based
Technical Analysis, Encyclopedia of Chart Patterns, Complete Guide to
Technical Trading Tactics, Algorithmic Trading, Harmonic Trading Vol 1,
Harmonic Trading Vol 2.

Options (2): Option Spread Strategies, Option Volatility & Pricing.

### Rejected alternatives
- **Single pool, rely on semantic similarity** — tested implicitly in the
  early system. Options passages ranked highly for some equity queries
  because the language of risk management overlaps. The tag is a hard
  filter that cannot be confused by embedding similarity.

---

## ADR-007 — Parallelization strategy: right tool for each context

**Date:** March 2026  
**Status:** Active

### Decision
Two different parallelization approaches for two different contexts:

**Backtest (`run_backtest.py`): `ProcessPoolExecutor`**
Each (strategy, ticker) job is independent. CPU-bound work (ta-lib,
pandas). Worker function is a top-level function (not method) for
pickle compatibility. `if __name__ == "__main__"` guard required.
Cap at `min(cpu_count, 8)` workers.

**Watchlist scanner (`/scan/watchlist`): `ThreadPoolExecutor`**
Each ticker scan is independent. I/O-bound bottleneck (yfinance HTTP).
Threads release during HTTP wait. Cap at `min(len(tickers), 10)` threads.
StrategyScanner instance shared — must be stateless (set in `__init__`,
never mutated after).

### Why ProcessPoolExecutor for backtest
CPU-bound work does not benefit from threads — the GIL prevents true
parallelism for Python bytecode. Processes each get their own interpreter.
Expected speedup: ~7 minutes → ~1-2 minutes on 8 cores.

### Why ThreadPoolExecutor for scanner
`asyncio` would require rewriting ta-lib calls as async (not possible).
`ProcessPoolExecutor` inside FastAPI forks the entire web server — wasteful
and potentially unstable. The bottleneck is yfinance HTTP requests which are
I/O-bound — threads release the GIL while waiting for network responses.
Expected speedup: ~80s → ~5s for 40 tickers.

### Why NOT a multi-agent framework
Considered and rejected for this use case. Each strategy's `evaluate()` is
a pure function — signal in, result out. Agent frameworks add coordination
overhead, retry logic, and latency for zero functional gain. The factory
pattern is already the correct abstraction. Multi-agent would be appropriate
only for Phase 7 portfolio-level reasoning (cross-asset synthesis across open
trades + new signals + options opportunities) — that requires genuine multi-step
reasoning, not just parallel execution.

### Hosting note
Backtest never runs on the hosted server — `validated_strategies.json` is
committed and read at startup. ProcessPoolExecutor speedup is local only.
ThreadPoolExecutor on the hosted scanner works correctly on any platform.

---

## ADR-008 — yfinance as data source: constraints and mitigation

**Date:** March 2026  
**Status:** Active

### Decision
yfinance is the primary data source for both backtest and live scanner.
The DB cache (`get_or_refresh_data()` in `market_data.py`) mitigates rate
limiting for the live scanner. The backtest uses direct yfinance calls
(no cache needed — runs locally, not on server).

### Constraints of yfinance
- No official API — it scrapes Yahoo Finance
- No API key, no SLA, no guaranteed uptime
- Intraday data: max 730 days, 4H is synthesised not native
- Rate limiting: Yahoo actively throttles high-frequency requests
- Daily data: reliable, split-adjusted, 10+ years, free

### Why accepted despite constraints
For daily swing trading strategies on a personal tool, yfinance daily data
is sufficiently reliable. The 10-year history supports meaningful backtesting.
The DB cache means the hosted server makes at most one yfinance call per
ticker per day — far below rate limit thresholds for a personal tool.

### The rate limiting problem at scale
If multiple users run `/scan/watchlist` simultaneously, the pattern becomes
`users × tickers` yfinance calls in a short window. Mitigation: the morning
briefing cron fetches data ONCE for the union of all users' watchlists,
caching results in the DB. All user scanner calls read from DB cache, not
yfinance directly. This collapses to `unique_tickers` calls regardless of
user count.

### Upgrade path
If yfinance reliability becomes a problem:
- **Daily data**: switch to Alpha Vantage ($50/mo) or EODHD — one-line
  change in `DataProvider` implementation
- **Live scanner**: switch to Alpaca free tier (real-time, same API for
  paper + live trading later)
- **Intraday (future)**: Alpaca or Polygon required — yfinance 4H is
  not reliable enough for live intraday signals

The `DataProvider` abstract class in `backtesting/data.py` was specifically
designed for this swap — add a new provider class, change one config line.

---

## ADR-009 — Intraday strategies deferred (S15-S17)

**Date:** March 2026  
**Status:** Deferred — revisit after daily strategies validated in paper trading

### Decision
VWAP reclaim (S15), Opening Range Breakout (S16), and 4H trend pullback
(S17) are documented in the strategy reference but not built in phases 1-6.

### Why deferred
1. **Data quality**: yfinance 4H is synthesised (aggregated), not native.
   Backtesting on synthesised bars produces unreliable results.
2. **Real-time data requirement**: VWAP and ORB require live intraday prices
   during the session. yfinance free tier has a 15-minute delay — unsuitable
   for live intraday signals.
3. **Infrastructure cost**: intraday monitoring requires the application to
   be running and checking signals throughout the trading session, not just
   at market open. This changes the hosting and notification requirements.
4. **Sequencing**: daily swing strategies should be validated in paper trading
   before adding intraday complexity. Adding intraday before daily strategies
   are proven adds risk without clear benefit.

### What is needed to un-defer
- Switch live data layer to Alpaca (free tier, real-time)
- Build intraday VWAP calculator that resets at market open
- Build session-open detector for ORB range establishment
- Add intraday monitoring loop (websocket or polling during session hours)
- Update hosting to run continuously during market hours

---

## ADR-010 — Frontend architecture: scanner-first, not lookup-first

**Date:** March 2026  
**Status:** Active

### Decision
The primary workflow is `ScannerPage` (proactive: shows what's setting up
across your watchlist) not `AnalysisPage` (reactive: you search a ticker).
`AnalysisPage` remains but is the drill-down view, not the entry point.

### Why
The original application was a lookup tool — you think of a ticker and
check it. The objective of a decision support tool for trading is the
opposite: it surfaces opportunities you should look at. The scanner page
implements the morning workflow: open app, see what fired overnight,
decide which to act on. `AnalysisPage` provides detail when you want
to investigate a specific result.

### Consequence for strategy panels
`StrategyPanel.tsx` is designed as a reusable component that renders any
`StrategyResult`. It appears in both the scanner list (compact) and the
analysis page (full detail). One component, two contexts.

### Rejected alternatives
- **Scanner as a separate app** — rejected. The analysis page, options
  scanner, and narrative synthesis are all useful for due diligence on
  a flagged setup. They should be one app, not two.

---

## ADR-011 — Trade tracker scope: log and alert only

**Date:** March 2026  
**Status:** Active

### Decision
The trade tracker logs trades you've taken, shows live R, and alerts when
exit conditions are met. It does not edit trades, does not compute portfolio
metrics, does not show charts, and does not manage orders.

### Why
The minimum useful feature set for a live trading assistant is: record what
I'm in, tell me when to get out. Portfolio analytics (Sharpe, drawdown curves,
correlation) are useful for review but not for real-time decision support.
Charts are already on the analysis page. Order management requires broker
integration (see ADR-001). Scope was deliberately constrained to what adds
value in the moment of a live trading session.

### What "exit alert" means specifically
- `APPROACHING_STOP`: current price within 2% of stop loss
- `AT_TARGET`: current price within 2% of target
- Strategy-specific exit signal (e.g. RSI >= 65 for S1)

These are surfaced in the nightly digest and on the trade tracker page.
They are not push notifications in phases 1-6 — the existing notification
system handles delivery.

### Upgrade path
Real-time exit alerts (push notification the moment price hits stop)
require websocket price feeds or polling during market hours.
Same infrastructure dependency as ADR-009 intraday deferral.

---

## ADR-012 — Position sizing: fixed fractional, enforced in code

**Date:** March 2026  
**Status:** Active

### Decision
Position size is computed as:
`shares = floor((account_size × risk_pct) / (entry_price - stop_loss))`

User sets `account_size` and `risk_pct` in their profile (default: $10,000
account, 1% risk). Computed automatically for every entry signal. Maximum
`risk_pct` enforced at 5% in the settings endpoint validation.

### Why
Fixed fractional position sizing is the standard risk management approach
for systematic trading. It ensures each trade risks a consistent dollar
amount regardless of stop distance. The 5% hard cap prevents a user from
accidentally configuring a position size that would be catastrophically large.

### What this does NOT do
- Does not account for existing open positions (portfolio heat)
- Does not adjust for volatility (ATR-based sizing)
- Does not enforce sector or correlation limits

These are Phase 7+ enhancements if the system proves out.

### Rejected alternatives
- **Fixed share size** — ignores stop distance, produces inconsistent risk
- **Kelly criterion** — requires accurate win rate and payoff estimates that
  are unreliable on small live samples
- **Volatility-adjusted sizing (ATR-based)** — better than fixed fractional
  in theory but adds complexity. Deferred until basic system is validated.

---

## ADR-013 — Multi-user architecture: personal tool first

**Date:** March 2026  
**Status:** Active

### Decision
The application supports multiple users (JWT auth, per-user watchlist,
per-user trade tracker, per-user account settings) but is designed and
optimized for personal use. It is not a SaaS product.

### Why
The infrastructure (Docker, Render, single PostgreSQL instance) is
appropriate for a small number of users. The yfinance data source
(see ADR-008) has rate limiting implications at scale. The Monte Carlo
options pricing is CPU-intensive and does not scale to concurrent users
on shared hosting.

### Practical implication
The morning briefing cron architecture (one data fetch per unique ticker
across all users, all scanner calls read from DB cache) is specifically
designed to keep yfinance call count low regardless of user count.

### What would be needed to productize
- Replace yfinance with a paid data API (Polygon, Alpha Vantage)
- Move Monte Carlo pricing to a background job queue (Celery + Redis)
- Add usage limits and billing
- Add admin dashboard and user management
- Load testing before any public launch

---

## ADR-014 — Backtest universe, train/test split, and tuning protocol

**Date:** March 2026  
**Status:** Active

### Decision
The backtest uses a 40-ticker expanded universe across 7 categories,
an 80/20 train/test split (2005–2021 train, 2021–2026 test), per-ticker
start dates using `max(2005-01-01, ticker_ipo)`, a two-stage gate, and
a structured 3-iteration tuning protocol for strategies that fail.

### Why 40 tickers across 7 categories

The original 18-ticker universe had three critical gaps that caused
specific strategy failures:

**Gap 1 — no volatile individual equities (caused S2 failure)**
Large-cap ETFs and mega-caps rarely hit RSI 30 on daily bars. S2 got
19 trades in 5 years — not enough to measure anything. Adding CRM, NFLX,
META, SQ, SLV, USO gives the strategy stocks that actually become oversold
on a regular basis.

**Gap 2 — no 2008-2009 recovery data (caused S10 ambiguity)**
S10 (Golden Cross Pullback) is specifically designed to catch the first
pullback after a major bear market bottom. The 2019-2024 window had no
meaningful bear-recovery cycle. Adding V, MA, UNH, HD and extending to
2005 gives S10 the 2009 recovery data it was designed for.

**Gap 3 — missing sectors (limited generalizability)**
No consumer discretionary, industrials, materials, staples, REITs, or
international exposure. Adding XLY, XLI, XLB, XLP, VNQ, EEM, EFA ensures
strategies are tested across different economic cycle sensitivities, not
just tech and financials.

**The 40-ticker cap**
Beyond 40 tickers, adding more names produces diminishing statistical
returns while increasing runtime significantly. Diversity across sectors
and volatility profiles matters more than raw count.

### Why 80/20 train/test (2005–2021 / 2021–2026)

**Train covers 4 distinct market regimes:**
- 2005-2007: pre-GFC bull market
- 2008-2009: Global Financial Crisis — most important bear market stress test
- 2009-2019: decade-long bull market
- 2020: COVID crash and rapid recovery

**Test covers 2 distinct regimes:**
- 2021-2022: post-COVID bull then Fed rate hike bear (different from 2008)
- 2023-2026: AI-driven recovery and bull market continuation

The test window deliberately includes a rate-driven bear market (2022)
which is mechanically different from the credit-driven 2008 crash. A
strategy that passes both is robust across different bear market types.

### Per-ticker start dates

Dropping TSLA because it starts in 2010 would lose a high-volatility
name that is valuable for S2 and S3. The `max(2005, ipo)` rule keeps
every ticker while being honest about available history. Tickers with
shorter history simply contribute fewer bars — they are not penalized,
they just have less influence on the aggregate statistics.

### Two-stage gate

Single-window backtesting has a well-documented problem: strategies that
look good on the full window are often optimized to it accidentally, even
when no explicit parameter search was done. The train/test split catches
this. A strategy that passes train (30+ trades, E > 0) but fails test
(20+ trades, E > 0) is either:
- Regime-sensitive: only works in certain market conditions → "pending"
- Curve-fitted: parameters tuned to 2005-2021 specifics → retire

Test gate is lower (20 trades vs 30) because the test window is shorter.

### Tuning protocol — 3-level classification, 3-iteration maximum

Before any parameter is changed, classify the failure:

**Level 1 — wrong universe (too few trades)**
Signal logic is fine but market conditions for the signal are rare in
the current universe. Fix: add more appropriate tickers. Do not change
strategy logic until you have sufficient trades to measure.

**Level 2 — parameter problem (right signal, wrong threshold)**
Signal fires at broadly the right times but the specific entry/exit
threshold is slightly off. Characterized by: reasonable trade count,
win rate near 50%, expectancy near zero. Fix: one parameter at a time,
max 3 iterations, full train re-run each time.

**Level 3 — structural failure (wrong signal entirely)**
Signal fires consistently and consistently loses. Characterized by:
high trade count, win rate well below 50%, large negative expectancy.
S8 StochasticCross (-2.35R on 519 trades) is the canonical example.
No amount of parameter tuning fixes a signal that fires on noise.
Retire immediately.

### Per-strategy tuning plans (Level 2 only)

**S2 RSI Mean Reversion** (if still fails after universe expansion):
1. Tighten stop from 1.5×ATR to 1.0×ATR
2. Add volume_ratio > 1.2× on entry bar
3. Require RSI < 35 two bars before the cross above 30

**S3 BB Squeeze** (if expectancy stays near zero):
1. Replace bb_upper close exit with ATR trailing stop
2. Tighten volume entry from 1.5× to 2.0×

**S10 Golden Cross Pullback** (if train passes, test fails):
1. Tighten "within 10 bars" to "within 5 bars"
2. Add weekly SMA10 > SMA40 confirmation at entry

### Hard tuning rules

1. Never tune on the test set — all parameter decisions made on TRAIN only
2. One parameter change per iteration — never change entry AND exit simultaneously
3. Maximum 3 iterations per strategy — after 3, retire or accept as-is
4. Each iteration requires full TRAIN re-run — no spot-checking
5. A strategy passes only when BOTH train AND test pass their respective gates
6. Train passes, test fails = curve fitted = retire (move to "retired") or
   pending (move to "pending" with a note about which regime it fails in)
7. All tuning attempts recorded in validated_strategies.json tuning_log
   regardless of outcome — the log is the audit trail

### Rejected alternatives

**Single window, no split** — rejected. Any strategy optimized even
slightly on the data it is tested on will show inflated results. The
2019-2024 window was this problem in practice: we got strong results
on 5 years that included one of the strongest bull markets in history.

**Rolling window cross-validation** — considered. Would give more
statistically robust results but requires 5-10× more compute and
significantly more complex implementation. The simple 80/20 split
catches the most important failure modes (regime sensitivity, curve
fitting) at a fraction of the complexity.

**Dropping short-history tickers** — rejected in favor of per-ticker
start dates. Dropping TSLA, V, META, SHOP loses valuable testing data
for specific strategies. The `max(2005, ipo)` rule is honest about
history without excluding useful names.

---


## ADR-015 — should_enter() and _check_conditions() must stay in sync

**Date:** March 2026  
**Status:** Active

### Decision
Every filter applied in `should_enter()` (the backtest interface) must have
a corresponding `Condition` object in `_check_conditions()` (the scanner
interface). The two methods must be logically equivalent. `_check_conditions()`
must be a complete superset of every filter in `should_enter()`.

### Why this rule exists

Discovered during Task 2.10 (S8v2 comparison). S8's `should_enter()` already
implemented `price > SMA200` filtering. The S8v2 comparison produced identical
results because the condition was already active in the backtest. This revealed
that `_check_conditions()` did not include the SMA200 condition — meaning the
live scanner could fire S8 signals on stocks below SMA200, which the backtest
never validated.

This is the most dangerous class of inconsistency in the system: the scanner
appears to work normally, the signals look valid, but they are operating outside
the validated envelope. There is no runtime error to catch it.

### The invariant

```
∀ condition C in should_enter():
    ∃ matching Condition in _check_conditions()
```

In plain terms: if `should_enter()` checks it, `_check_conditions()` shows it.

### How to enforce it

When writing a new strategy:
1. Write `should_enter()` first — this defines what the backtest validates
2. Write `_check_conditions()` as an explicit listing of every check in
   `should_enter()`, in the same order, with a Condition object for each
3. `evaluate()` calls `_check_conditions()` — the scanner sees exactly what
   the backtest tested

When modifying an existing strategy:
- Any change to `should_enter()` requires a matching change to `_check_conditions()`
- These two methods are coupled. Never edit one without reviewing the other.

### What to check in existing strategies

When Task 2.10 Step 5 runs, audit every strategy:
- Read `should_enter()` line by line
- Verify each condition has a Condition object in `_check_conditions()`
- Any gap = a hidden filter = a scanner/backtest inconsistency

### Consequence for S8 specifically

S8's `should_enter()` contains `price > SMA200`. This must be added as an
explicit Condition in `_check_conditions()`. The backtest numbers are already
correct (they already reflect the filter). Only the scanner interface needs
updating to make the filter visible.

---
## ADR-016 — Book strategy results are cached per (ticker, day), generation is on-demand

**Date:** March 2026
**Status:** Active

### Decision
The `knowledge_strategy_cache` table stores Claude's book strategy output keyed by `(ticker, cache_date)`. The `/analyze/{ticker}/knowledge-strategies` endpoint reads the cache before invoking Claude. On a cache hit, the Claude call is skipped entirely. On a miss, Claude is called, the result is written to cache, and returned.

On the frontend, the book analysis section is not fetched automatically on ticker search. Instead a "📚 Generate book analysis" button is shown. Clicking it triggers the fetch. If a cache hit exists the response is near-instant; otherwise the user waits the few seconds for Claude.

### Why

**Cost and latency**: Each `generate_strategies()` call sends ~8 retrieved passages to Claude and waits for a structured JSON response — typically 3–8 seconds and one API call. Triggering this automatically on every ticker search would be expensive and slow, especially when the user is quickly scanning multiple tickers.

**Same-day stability**: Market conditions don't change meaningfully within a trading day. A book strategy analysis generated at 09:30 is still valid at 15:30 for the same ticker. Per-day caching is the right granularity.

**On-demand UX**: The user may not always want book analysis for every ticker they look up. Making it a button respects that. If they do want it, the cached path makes it instant on repeated access.

### Cache design constraints
- Primary key on `(ticker, cache_date)` — one row per ticker per day
- `ON CONFLICT DO NOTHING` on write — concurrent requests on the same ticker/day are safe
- No expiry logic — historical entries are a permanent record of what the model said on a given day
- Cache write failure is silently swallowed — a DB error must never break the API response

### Consequence for the frontend
`handleSearch` in `AnalysisPage.tsx` resets `bookStrategies` and `bookError` to null when a new ticker is searched (so stale results don't carry over). The `isLoadingBook` state is only set to true by `handleGenerateBook`, never by `handleSearch`.

### Rejected alternatives
- **Auto-fetch on search, no cache** — original implementation. Blocked the UX on slow tickers and re-called Claude identically every time the user revisited a ticker in the same session.
- **Cache with TTL / daily expiry job** — rejected. Old entries are historical record, not garbage. There is no cost to keeping them. A TTL job adds complexity for no benefit.
- **Session-only cache (React state)** — rejected. Does not survive page refresh and wastes a Claude call on every session open.

---

## ADR-019 — Backplayer merge: frozen file exceptions and new signal layers

**Date:** March 2026  
**Status:** Active

### Decision
The backplayer feature (commit 1b7de72) modified two files that were
previously frozen: `app/services/ta_engine.py` and `app/services/market_data.py`.
These changes are accepted. The frozen status of both files is updated to
reflect the new additions.

### What changed in frozen files

**`app/services/ta_engine.py`**
- `analyze_ticker()` gains an optional `hourly_df` parameter (default None)
- When `hourly_df` is provided, computes `FourHConfirmation` and appends
  `four_h_confirmation` and `four_h_upgrade` to `AnalysisResponse`
- All existing signal logic (swing_setup weights, candlestick patterns,
  trend/momentum/volume/S/R computations) is unchanged
- The addition is additive and gated — passing `hourly_df=None` produces
  identical output to the pre-merge version

**`app/services/market_data.py`**
- Added `fetch_hourly_data()`, `_upsert_hourly()`, `_is_hourly_stale()`,
  `get_or_refresh_hourly_data()` — all new functions
- No existing functions modified
- Hourly data stored in new `hourly_price_history` table

### Why accepted despite freeze

The spirit of the freeze was to protect signal scoring weights and
calibrated logic from accidental modification. The backplayer changes
are purely additive — they add a new signal layer (4H confirmation)
without touching any existing weights, conditions, or scoring logic.
The freeze protected against drift; this is a deliberate extension.

### Updated freeze scope

Both files remain frozen with this clarification:
- `ta_engine.py`: all existing signal functions frozen. The `hourly_df`
  parameter and `FourHConfirmation` computation are frozen as new
  additions. Do not modify swing_setup weights, candlestick patterns,
  or any existing compute_* function.
- `market_data.py`: all existing functions frozen. The hourly functions
  are frozen as new additions. Do not modify `get_or_refresh_data()`,
  `fetch_ticker_data()`, or any existing data pipeline function.

### New tables added by backplayer

- `backtest_runs` — one row per player backtest run with parameters and
  aggregate stats (win rate, expected value, P&L in fixed and compound modes)
- `backtest_signals` — one row per signal fired during a run with full
  signal context at entry and outcome evaluation (WIN/LOSS/EXPIRED)
- `hourly_price_history` — 1H OHLCV bars, refreshed every 2 hours

---

## ADR-020 — Three new signal layers available for strategy factory integration

**Date:** March 2026  
**Status:** Pending integration — query backtest_signals before implementing

### Decision
Three new signals introduced by the backplayer merge are available in
the `SignalSnapshot` but not yet used by any strategy in the factory.
Integration is deferred until empirical evidence from `backtest_signals`
data confirms their impact on outcomes.

### The three new signals

**1. Four-hour confirmation (`four_h_upgrade`, `four_h_confirmation`)**

Computed by `ta_engine.py` when `hourly_df` is provided. Fires True when:
- A bullish reversal candle exists on the 4H chart
- A 4H trigger bar (close > prior 4H high) has fired
- 4H RSI is in an acceptable range

`four_h_upgrade = True` means daily signal AND 4H signal are aligned.
This addresses the failure mode where a daily ENTRY fires but price
continues lower because the 4H timeframe had not yet confirmed the reversal.

**2. R:R gate in SwingConditions (`rr_label`, `rr_gate_pass`)**

Added to `SwingConditions` model. Labels the R:R ratio as
good/marginal/poor/bad/unavailable. Currently computed by `backtester.py`
but the field exists in `swing_setup.conditions` in the snapshot.
A setup with `rr_label = "bad"` (R:R < 0.5) currently scores identically
to one with `rr_label = "good"` (R:R > 2.0). This is wrong — poor R:R
should reduce score or suppress ENTRY.

**3. Provisional S/R flag (`support_is_provisional`)**

`argrelextrema(order=5)` requires 5 confirmed bars on each side of a
swing low. Very recent lows are flagged `support_is_provisional = True`.
A stop placed at a provisional support is less reliable than one at a
confirmed level. `_stop_is_valid()` currently treats both equally.

### Why deferred — evidence first

The `backtest_signals` table contains `four_h_upgrade`, `rr_label`, and
`support_is_provisional` columns alongside outcome data (WIN/LOSS/EXPIRED,
return_pct, MAE, MFE). Before adding any of these as score modifiers, query
the actual outcome data to confirm each signal's empirical impact:

```sql
-- Does four_h_upgrade correlate with better outcomes?
SELECT four_h_upgrade,
       COUNT(*) as trades,
       AVG(CASE WHEN outcome='WIN' THEN 1.0 ELSE 0.0 END) as win_rate,
       AVG(return_pct) as avg_return
FROM backtest_signals
WHERE outcome IS NOT NULL
GROUP BY four_h_upgrade;

-- Does rr_label predict outcomes?
SELECT rr_label,
       COUNT(*) as trades,
       AVG(CASE WHEN outcome='WIN' THEN 1.0 ELSE 0.0 END) as win_rate,
       AVG(return_pct) as avg_return
FROM backtest_signals
WHERE outcome IS NOT NULL
GROUP BY rr_label
ORDER BY avg_return DESC;

-- Does provisional support affect stop reliability?
SELECT support_is_provisional,
       AVG(mae) as avg_mae,
       AVG(CASE WHEN outcome='WIN' THEN 1.0 ELSE 0.0 END) as win_rate
FROM backtest_signals
WHERE outcome IS NOT NULL
GROUP BY support_is_provisional;
```

Integration decisions will be made based on query results, not assumption.

### Proposed integration homes (pending evidence)

| Signal | Proposed home | Proposed effect |
|--------|--------------|-----------------|
| `four_h_upgrade` | `_check_conditions()` optional condition | Score bonus when True, no penalty when False or unavailable |
| `four_h_available` | `_check_conditions()` display only | Show when 4H data was not available so user knows upgrade check didn't run |
| `rr_label` | `_compute_risk()` | bad R:R returns None (no trade). poor reduces score. good/marginal pass through. |
| `rr_gate_pass` | `_verdict()` | False suppresses ENTRY regardless of other conditions |
| `support_is_provisional` | `_stop_is_valid()` | Provisional support requires wider threshold (0.75×ATR instead of 0.5×ATR) |

### What does NOT change

- Existing strategy backtest results remain valid — none of these filters
  were applied during the train/test runs in validated_strategies.json
- If any filter is added, the affected strategies must be re-backtested
  to measure the impact on expectancy and trade count
- The validated_strategies.json gate (E > 0, trades >= 30/20) applies
  to the re-run just as it did to the original
---
## Open questions — not yet decided

These are decisions that will need to be made as the system evolves.
Record the decision here when made.

**OQ-001: Portfolio heat management**
Should the scanner suppress new ENTRY signals when existing open trades
already have the account X% exposed? If yes, what threshold and what logic?
Relevant when: Phase 7 or when first paper trade causes concern about
over-exposure.

**OQ-002: Strategy weight decay / re-validation cadence**
How often should strategies be re-backtested? Markets change and historical
edge can decay. Monthly? Quarterly? Only when live win rate diverges from
backtest win rate by >10%? No decision yet.

**OQ-003: Short-selling strategies**
The signal engine computes death cross, bearish OBV divergence, and other
bearish signals. S13 (OBV divergence fade) is a short setup. Adding short
strategies to the scanner requires broker support for short selling and
different risk management (unlimited downside). Deferred until long-only
strategies are proven.

**OQ-004: Alpaca migration timing**
When does it make sense to switch the live data layer from yfinance to
Alpaca? Triggers: yfinance reliability degrades, intraday strategies
are ready to build, or live execution is added. The DataProvider abstraction
in `backtesting/data.py` makes this a one-class change.

**OQ-005: Phase 7 portfolio reasoning**
Multi-step reasoning across open trades + new signals + options opportunities.
This is the one place where a multi-agent pattern (gather context → reason →
recommend) would be genuinely better than a single prompt. Not designed yet.
