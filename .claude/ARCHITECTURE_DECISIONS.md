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
