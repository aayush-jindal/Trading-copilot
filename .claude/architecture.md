# Architecture reference

## Application objective
Personal trading decision support tool. Proactive scanner across user's
watchlist. Surfaces validated strategy setups ranked by conviction.
Provides entry/stop/target/position sizing. Tracks open trades for exit alerts.

## Two scoring systems — never mix them

| System | File | Purpose | Do not modify |
|--------|------|---------|---------------|
| Equity swing setup | ta_engine.py `compute_swing_setup_pullback()` | S1 entry signal source | FROZEN |
| Options bias | bias_detector.py `detect_bias()` | Options direction | FROZEN |

## Strategy factory — the core pattern

```
backtesting/
  strategies/
    base.py          ← BaseStrategy + Condition + RiskLevels + StrategyResult dataclasses
    registry.py      ← STRATEGY_REGISTRY list — one line per active strategy
    s1_trend_pullback.py
    s2_rsi_reversion.py
    ... one file per strategy, forever
  scanner.py         ← StrategyScanner.scan(ticker, account_size, risk_pct)
  data.py            ← DataProvider + YFinanceProvider
  signals.py         ← SignalEngine wrapping ta_engine (read-only)
  engine.py          ← BacktestEngine (bar-by-bar replay)
  results.py         ← ResultsAnalyzer + passes_gate()
```

## Key file map

```
app/
  services/
    ta_engine.py          ALL equity signals — FROZEN
    market_data.py        yfinance + DB cache — FROZEN
    ai_engine.py          prose narrative — FROZEN
    options/
      bias_detector.py    options scoring — FROZEN
      scanner.py          options orchestrator
      pricing/src/**      BS/MC/LSMC library — FROZEN
  routers/
    analysis.py           GET /analyze/{ticker}
    synthesis.py          GET /synthesize/{ticker} SSE — FROZEN
    options.py            POST /options/scan
    strategies.py         NEW phase3 — GET /strategies/{ticker}
    watchlist_scan.py     NEW phase4 — GET /scan/watchlist

tools/
  knowledge_base/
    retriever.py          pgvector search
    strategy_gen.py       RAG → Claude → strategies

frontend/src/
  components/
    SwingSetupPanel.tsx   EXISTS — do not modify
    StrategyPanel.tsx     NEW phase6 — reusable, color-coded
  pages/
    AnalysisPage.tsx      EXISTS — add StrategyPanel slots in phase6
    ScannerPage.tsx       NEW phase6 — primary morning workflow
    TradeTrackerPage.tsx  NEW phase6 — open positions dashboard
```

## Color coding by strategy type
- teal    = trend following  (S1 S6 S7 S9 S10)
- purple  = mean reversion   (S2 S8 S11 S13)
- amber   = breakout         (S3 S12 S14)
- blue    = rotation/factor  (S4 S5)

## Design principles
- Adding a strategy = one new file + one registry line. Nothing else.
- Scanner reads only validated strategies (passed backtest gate).
- Math decides (scorer). Claude explains (RAG). Never reversed.
- All new routes follow existing JWT auth pattern in main.py.
- No feature added without explicit instruction in active phase file.
