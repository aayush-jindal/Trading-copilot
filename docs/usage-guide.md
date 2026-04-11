# Trading Copilot — Usage Guide

A personal trading decision support tool that scans your watchlist,
surfaces validated strategy setups ranked by conviction, provides exact
entry/stop/target/position sizing, and tracks open trades for exit alerts.

---

## Getting Started

1. **Login** at the root URL. Create an account or use the default
   credentials configured in your environment.
2. **Build your watchlist** — go to the Watchlist page and add tickers
   you want to track (e.g. AAPL, SPY, MSFT).
3. **Run the Morning Scan** — navigate to `/scanner` to see what's
   firing today across both equity strategies and options signals.

---

## Pages

### Analysis (`/`)

The main research hub. Enter a ticker in the search bar to get:

- **Price chart** — 1-year daily candlestick chart.
- **Technical signals** — trend (SMA/EMA crossovers), momentum (RSI,
  MACD, stochastic), volatility (Bollinger Bands, ATR, squeeze), and
  volume analysis.
- **Swing setup** — the system evaluates whether conditions meet a
  swing entry. Verdicts are **ENTRY**, **WATCH**, or **NO_TRADE** with
  a 0-100 setup score. Entry/stop/target levels and position size are
  provided when a trade fires.
- **AI narrative** — a real-time streamed synthesis that reads all
  signal layers and produces a plain-English summary with action items.
- **Strategy scanner tab** — runs all validated strategies (S1 through
  S10) against the ticker and shows which are firing.
- **Chain scanner tab** — scans the options chain for mispriced
  contracts, showing IV rank, GARCH edge, conviction scores, and
  recommended option strategies with exact pricing.

### Watchlist (`/watchlist`)

A dashboard of all your tracked tickers showing current price, daily
change, and trend signal at a glance. Click any card to jump to
the full analysis. Add or remove tickers with the modal.

### Morning Scan (`/scanner`)

Your daily starting point. Two modes:

- **Equity mode** — runs the equity strategy scanner across your
  entire watchlist. Shows each strategy firing, its verdict, score,
  and exact risk levels.
- **Unified mode** (default) — runs **both** the equity scanner and
  the options chain scanner in parallel, then merges the results into
  a single ranked list.

**How to read the unified scan:**

| Badge | Meaning |
|-------|---------|
| `Equity` (teal) | Signal from an equity strategy (S1, S2, etc.) |
| `Options` (indigo) | Signal from the options chain scanner |
| `+ Options` or `+ S1_TrendPullback` (green) | **Correlated signal** — both scanners agree on this ticker. Options conviction is boosted by 15%. |
| Yellow hedge banner | You have an open equity trade on this ticker and cheap puts are available (LOW IV regime). Consider a protective put. |

Correlated signals sort to the top. Within each group, signals are
ranked by conviction (options) or score (equity) descending.

### Options Scanner (`/options`)

A standalone options analysis page. Enter tickers and optionally filter
by directional bias and time horizon. Shows multi-leg strategies with
full Greeks, probability of profit, and entry/exit levels.

### Trade Tracker (`/trades`)

Manage both equity and option positions:

- **Equity trades** — entry price, stop, target, shares, current
  R-multiple (how many risk units you're up or down), and exit alerts.
- **Option trades** — strategy name, legs with strikes, credit/debit,
  P&L, DTE remaining, and automated exit alerts (stop hit, target
  reached, expiry warning, theta decay).

Log trades directly from the chain scanner's "Log Trade" button or
manually from the trades page.

### Backtester (`/player`)

Run historical simulations of equity strategies:

1. Select a ticker and strategy (S1 through S10).
2. Set lookback period, score thresholds, and risk parameters.
3. View results on an interactive chart with entry/exit markers,
   equity curve, and trade-by-trade breakdown.

---

## Key Concepts

### Signal Layers

The system computes multiple independent signal layers on every
analysis call. These are available in the analysis view and drive
all strategy decisions:

| Layer | What it tells you |
|-------|-------------------|
| **Trend** | SMA50/200, EMA9/21, golden/death cross |
| **Momentum** | RSI, MACD, stochastic — overbought/oversold |
| **Volatility** | ATR, Bollinger Bands, squeeze detection |
| **Volume** | Volume ratio vs 20-day avg, OBV trend |
| **Support/Resistance** | Nearest S/R levels, strength, provisional flags |
| **Weekly** | Weekly trend direction and strength |
| **4H confirmation** | When hourly data exists, confirms daily + 4H alignment |

### IV Rank and Regime

The options chain scanner classifies each ticker's implied volatility:

| Regime | IV Rank | What it means |
|--------|---------|---------------|
| **LOW** | 0-25 | Options are cheap. Favor buying strategies (long calls/puts, debit spreads). |
| **NORMAL** | 25-60 | No strong edge from volatility alone. |
| **ELEVATED** | 60-80 | Options are getting expensive. Mixed strategies. |
| **HIGH** | 80-100 | Options are expensive. Favor selling strategies (credit spreads, iron condors). |

After 30+ days of IV history accumulation, the rank switches from a
realized-vol proxy to **real IV rank** (computed from actual ATM IV
snapshots). The chain scanner shows a "Real IV" or "Proxy IV" badge
to indicate which mode is active.

### Conviction Score

Options signals are scored 0-100 based on:

| Factor | Weight | What drives it up |
|--------|--------|-------------------|
| **Edge** | 40% | Larger mispricing between GARCH theo price and market mid |
| **IV rank** | 25% | Alignment of IV regime with direction (HIGH + SELL, LOW + BUY) |
| **Liquidity** | 20% | Tight bid-ask spread, high open interest |
| **Greeks** | 15% | Favorable theta/vega profile for the direction |

When both the equity scanner and options scanner fire on the same
ticker (correlation), the options conviction gets a **15% boost**
(capped at 100).

### Strategy Verdicts

Equity strategies produce one of three verdicts:

- **ENTRY** — all conditions met, entry/stop/target provided.
  Consider taking the trade.
- **WATCH** — most conditions met but something is missing (e.g.
  no reversal candle yet, R:R too tight). Monitor for improvement.
- **NO_TRADE** — conditions not met. Skip.

### Hedge Suggestions

When you have an open equity position and the options scanner detects
LOW IV on that same ticker, the unified scan suggests a protective
put. This means options are cheap relative to their history — a good
time to buy insurance.

---

## Daily Workflow

1. **Open the Morning Scan** (`/scanner`) in Unified mode.
2. **Review correlated signals first** (green badges at the top).
   These have the highest conviction because both scanners agree.
3. **Check hedge suggestions** — if you have open equity trades and
   the scan suggests protective puts, evaluate whether to hedge.
4. **Drill into interesting tickers** — click any row to open the
   full analysis page with chart, signals, and AI narrative.
5. **Log trades** — when you decide to enter, use the "Log Trade"
   button on the chain scanner's priced strategy cards, or log
   manually on the trades page.
6. **Monitor open trades** — the trades page shows live P&L and
   will alert you when positions approach stops or targets.

---

## Nightly Automation

The system runs a nightly job that:

1. Refreshes price data for all watchlisted tickers.
2. Runs the chain scanner and stores signals.
3. Stores ATM IV snapshots into `iv_history` (builds up real IV rank
   over time).
4. Reprices open option trades and generates exit alerts as
   notifications.

You don't need to do anything — cached results appear automatically
when you load the chain scanner tab. The "Last scanned" timestamp
shows when the nightly run completed.

---

## Ticker Compatibility

Not all tickers work equally well with all strategies. Based on
backtesting 10,906 signals across 30 tickers:

**S1 (Trend Pullback) compatible** — steady trend, reliable S/R:
```
SPY  QQQ  AAPL  MSFT  COST  WMT  MCD  TXN
NOW  AVGO  JPM   V    MA    UNH  HD   GOOGL
NFLX PANW  MU   SHOP  PYPL
```

**S1 incompatible** — too volatile or unreliable S/R:
```
MSTR  TSLA  COIN  INTC  ORCL  SNAP
```

These may still work with S2 (RSI mean reversion) or S8 (stochastic
cross). The system warns you when you run an incompatible combination.

---

## Tips

- **Start with the unified scan** rather than analyzing tickers one
  by one. It surfaces what matters across your whole watchlist.
- **Pay attention to IV regime** — it determines whether you should
  be buying or selling options. Don't buy options in HIGH IV unless
  you have a strong directional conviction.
- **Correlated signals are the highest quality** — when both equity
  and options scanners agree, the setup has multiple confirming
  factors.
- **Use the backtester** to validate strategies on your tickers
  before risking real capital.
- **Real IV rank improves over time** — the longer you run the
  system, the more IV history accumulates, and the more accurate
  the IV rank becomes. After 30 days it switches from proxy to real.
- **Check the AI narrative** for nuance the numbers might miss — it
  reads all signal layers and can flag conflicting signals or
  unusual patterns.
