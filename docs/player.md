# Backtesting Player — User Guide

The Player is a historical replay tool for the swing setup engine. It walks
through price history bar by bar, fires the same signals the live analysis page
uses, and evaluates what actually happened after each signal. Use it to
understand how the swing setup scorer performs on a specific ticker before
acting on live signals.

Navigate to it from the header: **Backtester** → `/player`

---

## How it works

For each trading day in your chosen date range, the Player runs the full TA
engine as if it were that day (no future data leaks in). Every time the engine
fires an `ENTRY` or `WATCH` verdict, it records the signal and then looks
forward up to **30 calendar days** to resolve the outcome:

- **WIN** — price reached the target before the stop
- **LOSS** — price hit the stop before the target
- **EXPIRED** — neither level was hit within 30 days (exits at day-30 close)

---

## Controls

All controls are in the right panel. After setting them, click **Run Backtest**.

### Date range

Use the quick presets (6M, 1Y, 2Y, 3Y) or enter a custom from/to date. Longer
ranges produce more signals and more statistically reliable results. A minimum
of 1 year is recommended.

### Entry score threshold (default: 70)

The minimum setup score for a signal to be labelled `ENTRY`. The score is
computed by `ta_engine.py` and reflects how many bullish conditions are aligned:
uptrend, near support, reversal candle, trigger bar, weekly alignment, etc.

- **Higher (80–90)** → fewer signals, more selective, should have higher win rate
- **Lower (55–65)** → more signals, worth comparing win rate to see if quality drops

### Watch score threshold (default: 55)

Signals scoring above this but below the entry threshold are labelled `WATCH`.
Signals below both thresholds are `NO_TRADE` and are not recorded.

### Min R:R ratio (default: 1.5)

Minimum reward-to-risk ratio required. Calculated as
`(target − entry) / (entry − stop)`. Signals with R:R below this are suppressed
regardless of score.

- **1.5** — target must be 1.5× the stop distance away
- **2.0** — more conservative, fewer signals but better expected value per trade

### Min support strength (default: LOW)

Filters signals where the nearest support level is weak. The engine classifies
support as LOW / MEDIUM / HIGH based on how many swing lows cluster near that
price. Setting this to MEDIUM or HIGH reduces signals that have a stop resting
on flimsy support.

### Require weekly aligned (default: ON)

When enabled, only records signals where the weekly trend is also bullish (price
above weekly SMA10, SMA10 above SMA40). This is the most powerful single filter:
trading with the weekly trend significantly improves win rate but cuts signal
frequency.

### Run label

Auto-generated as `TICKER · E{entry} · W{watch} · RR{rr} · S-{support} · W-{ON|OFF}`.
You can rename it to something descriptive before running. Labels appear in the
runs list so you can compare multiple parameter sets on the same ticker.

---

## Reading the results

### Summary stats

| Stat | What it means |
|------|--------------|
| **Total signals** | All ENTRY + WATCH signals fired in the period |
| **Entry / Watch** | Breakdown by verdict |
| **Win / Loss / Expired** | Outcome breakdown |
| **Win rate** | Wins ÷ (Wins + Losses). Excludes EXPIRED — this is the true win rate. |
| **Win rate ENTRY** | Win rate for ENTRY-only signals. Should be higher than WATCH. |
| **Expected value** | `(win_rate × avg_win%) − (loss_rate × avg_loss%)`. Positive = system has edge on this ticker/period. The single most important number. |
| **Avg return %** | Mean return across all signals including EXPIRED. |
| **Avg MAE** | Average Maximum Adverse Excursion — how far against you each trade moved before resolving. If MAE ≈ stop distance, stops are well-placed. If MAE > stop distance consistently, stops are too tight. |
| **Avg MFE** | Average Maximum Favorable Excursion — how far in your favour each trade moved. If MFE is much larger than avg return %, the target is too conservative and you're leaving gains on the table. |
| **Avg days to outcome** | How long trades typically take to WIN or LOSS. Affects capital allocation — a 20-day average tie-up is very different from 5 days. |
| **Fixed P&L** | Total dollar P&L starting with $1,000 per ENTRY trade, same size every trade. |
| **Compound P&L** | Total dollar P&L starting with $1,000 and reinvesting profits / absorbing losses on each ENTRY trade. Shows geometric growth potential. |

### What good results look like

| Metric | Target |
|--------|--------|
| Expected value | > 0 (any positive edge is useful) |
| Win rate (ENTRY) | > 50% |
| Avg MFE vs avg return | MFE should be ≥ 2× avg return — confirms targets are reachable |
| Avg MAE vs stop distance | MAE should be < stop distance — confirms stops aren't just noise |
| Expired % | < 40% — if most signals never resolve, the setup doesn't have a clear catalyst |

---

### The price chart

- **Green triangles (▲)** — ENTRY signals
- **Yellow triangles (▲)** — WATCH signals
- **Green ✓** — WIN outcome
- **Red ✗** — LOSS outcome

Clicking any marker on the chart jumps to that signal's row in the table below.
Pan and zoom the chart to focus on a specific period.

### P&L chart

Shows the running P&L curve over time for ENTRY signals only.

- **Blue line** — fixed $1,000 per trade
- **Green line** — compounding

The P&L chart is time-synced to the price chart — zooming one zooms the other,
so you can see which market regimes drove gains or losses.

### Signals table

Each row is one signal. Click a row to highlight it on the chart and expand
entry/stop/target prices.

| Column | Meaning |
|--------|---------|
| **Date** | Day the signal fired |
| **Verdict** | ENTRY or WATCH |
| **Score** | Raw setup score |
| **Decile** | Score percentile bucket (1=lowest, 10=highest) |
| **↑trend** | Uptrend confirmed (price above SMA50) |
| **W↑** | Weekly trend aligned bullish |
| **Near S** | Near a support level |
| **Rev** | Bullish reversal candle present |
| **Trig** | Trigger bar fired (close above prior swing high) |
| **R:R** | Reward:risk ratio for this specific setup |
| **Outcome** | WIN / LOSS / EXPIRED |
| **Return %** | Actual % return from entry to exit price |
| **MAE** | Max adverse excursion for this trade |
| **MFE** | Max favorable excursion for this trade |

---

## Comparing runs

You can run the same ticker multiple times with different thresholds. All
previous runs are saved and shown in the runs list. Use custom labels to track
what you changed. Useful comparisons:

**Weekly filter on vs off**
```
AAPL · E70 · W55 · RR1.5 · S-LOW · W-ON   ← fewer signals, check if win rate improves
AAPL · E70 · W55 · RR1.5 · S-LOW · W-OFF  ← more signals, baseline
```

**Score threshold sensitivity**
```
AAPL · E60 · W45 · RR1.5 · S-LOW · W-ON   ← permissive
AAPL · E75 · W60 · RR1.5 · S-LOW · W-ON   ← selective
```

**R:R filter impact**
```
AAPL · E70 · W55 · RR1.0 · S-LOW · W-ON   ← accepts poor R:R setups
AAPL · E70 · W55 · RR2.0 · S-LOW · W-ON   ← requires good R:R only
```

---

## Limitations

- **Lookahead cap is 30 days.** Signals that don't resolve in 30 days are
  EXPIRED. Long-duration swings may be misclassified. Check `avg_days_to_outcome`
  — if it's close to 30, consider that many wins may be expiring just before
  they'd have resolved.

- **No slippage or commissions.** Entry is at the signal bar's closing price.
  In practice you'd enter on the next open, typically slightly higher.

- **One signal per bar.** If the engine fires on consecutive days, each is
  recorded independently. In live trading you'd only take one position per ticker
  at a time.

- **Daily data only.** The 4H confirmation layer (`four_h_upgrade`) requires
  hourly data which may not be available for all historical dates.

- **Data is cached.** If yfinance returns stale data for a ticker, the backtest
  reflects that. For recent runs (< 4 hours old) data is fresh.

---

## Data this generates

Every run populates the `backtest_signals` database table with signal context
and outcomes. This data is used to empirically validate whether signals like
`four_h_upgrade`, `rr_label`, and `support_is_provisional` actually improve
outcomes — see ADR-020 in `.claude/ARCHITECTURE_DECISIONS.md` for the analysis
plan and the SQL queries to run once enough data accumulates.
