# Phase F — Equity + Options Signal Correlation

## Goal

When a ticker fires both an equity strategy signal (S1/S2/S8) and a
chain scanner signal, correlate them in a unified view with boosted
conviction.

---

## What to build

### Unified signal endpoint

```
GET /scan/unified?top=20
```

Runs both the equity scanner (`scanWatchlist`) and the chain scanner,
merges results, and cross-references:

```python
def merge_signals(equity_signals, option_signals):
    # Group by ticker
    for ticker in all_tickers:
        equity = [s for s in equity_signals if s.ticker == ticker]
        options = [s for s in option_signals if s.ticker == ticker]

        if equity and options:
            # Both firing — boost conviction
            for o in options:
                o.conviction = min(o.conviction * 1.15, 100)
                o.correlated_equity_signal = equity[0].name

        # Hedge suggestion: long stock + HIGH IV → suggest protective put spread
        if equity and any(e.verdict == 'ENTRY' for e in equity):
            if any(o.iv_regime == 'LOW' and o.direction == 'BUY' for o in options):
                # Cheap puts available — suggest hedge
                pass
```

### Unified frontend page

Extend the Morning Scan page (`ScannerPage.tsx`) or create a new
unified page showing equity + options signals in a single ranked list.
Each row shows: ticker, signal source (equity/options/both), strategy,
conviction, entry/stop/target.

### Hedge suggestions

When the user has an open equity trade (from `open_trades`) and
the chain scanner finds cheap puts (LOW IV regime), suggest a
protective put or put spread as a hedge.

---

# Phase G — Alerts + Notifications

## Goal

Push options-specific alerts into the existing notification system.

---

## Alert types

| Alert | Trigger | Priority |
|-------|---------|----------|
| IV rank alert | IV rank crosses above 80 or below 20 | Medium |
| High conviction signal | New signal with conviction > 70 | High |
| Position expiry warning | Open option trade DTE < 7 | High |
| Stop hit | Open option trade loss > stop level | Critical |
| Target reached | Open option trade profit > target | High |
| Theta decay warning | Debit position with DTE < 14 | Medium |

## Implementation

### Nightly alert generation

Add to nightly refresh, after repricing option trades:

```python
def generate_option_alerts(user_id: int) -> list[dict]:
    alerts = []

    # 1. Check open option trades for exits
    trades = get_open_option_trades(user_id)
    for trade in trades:
        repriced = reprice_trade(trade)
        if repriced.exit_alert:
            alerts.append({
                "type": "option_exit",
                "ticker": trade.ticker,
                "message": f"{trade.ticker} {trade.strategy}: {repriced.exit_alert}",
                "priority": "high",
            })

    # 2. Check latest chain scan for high conviction
    signals = get_latest_signals(user_id)
    for s in signals:
        if s.conviction > 70:
            alerts.append({
                "type": "option_signal",
                "ticker": s.ticker,
                "message": f"{s.ticker}: {s.direction} {s.option_type} — {s.conviction:.0f}% conviction",
                "priority": "medium",
            })

    return alerts
```

### Store as notifications

Use the existing `notifications` table:

```python
for alert in alerts:
    conn.execute("""
        INSERT INTO notifications (user_id, type, title, body, created_at)
        VALUES (%s, %s, %s, %s, NOW())
    """, (user_id, alert["type"], alert["ticker"], alert["message"]))
```

### Frontend

The existing `NotificationsPanel.tsx` already renders notifications.
Add icon/color mapping for the new notification types:
- `option_exit` → red warning icon
- `option_signal` → green signal icon

---

# Phase H — Backtesting Options Strategies

## Goal

Validate whether the chain scanner's signals actually produce positive
returns historically.

---

## Approach

### Data source

Use the `iv_history` table (from Phase E) plus historical price data
(already in `price_history` table) to reconstruct what the scanner
would have signaled in the past.

### Backtest engine

```python
def backtest_chain_scanner(
    ticker: str,
    start_date: str,
    end_date: str,
    strategy_filter: str = None,  # e.g. "short_put_spread"
) -> dict:
    """
    For each historical date:
    1. Look up IV from iv_history
    2. Compute what IV rank would have been at that point
    3. If IV rank > threshold → simulate opening the recommended trade
    4. Track the trade forward to exit/expiry
    5. Record P&L
    """
```

### Key metrics

```python
{
    "total_trades": 142,
    "wins": 98,
    "losses": 44,
    "win_rate": 69.0,
    "avg_return_pct": 4.2,
    "max_drawdown_pct": -12.5,
    "sharpe_ratio": 1.8,
    "avg_days_held": 28,
    "best_regime": "HIGH",      # which IV regime produced best results
    "best_strategy": "short_put_spread",
    "conviction_correlation": 0.42,  # does higher conviction → better outcome?
}
```

### API endpoint

```
POST /options/backtest
{
    "ticker": "AAPL",
    "start_date": "2025-04-01",
    "end_date": "2026-04-01",
    "min_conviction": 50,
    "strategy": "short_put_spread"
}
```

### Frontend

Add a "Backtest" tab or section showing:
- Cumulative P&L chart over time
- Win rate by IV regime
- Win rate by strategy
- Conviction vs outcome scatter plot
- "The scanner's HIGH+SELL signals had a 72% win rate over the past year"

### Requirements

- Phase E (IV history) must have 6+ months of data before backtesting
  is meaningful
- This is a later phase — don't build until IV history has accumulated

---

## Phase order and dependencies

```
Phase D (trade tracker)    — no dependencies, build now
Phase E (IV history)       — no dependencies, build now
Phase F (correlation)      — needs D + equity scanner
Phase G (alerts)           — needs D + E
Phase H (backtesting)      — needs E with 6+ months of data
```

D and E can be built in parallel. F and G depend on D.
H is a long-term play that improves as IV history accumulates.
