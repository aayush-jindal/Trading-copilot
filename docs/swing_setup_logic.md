# Swing Setup: Pullback in Uptrend — Logic Reference

**Setup type:** `pullback_in_uptrend`
**Timeframe:** Daily bars
**Implementation:** `app/services/ta_engine.py` → `compute_swing_setup_pullback()`

---

## Overview

The detector looks for a single high-probability scenario: a stock that is in a clear uptrend, has pulled back toward support on declining volume, and is starting to reverse with a trigger bar. All seven conditions are scored independently and combined into a 0–100 score. The verdict (ENTRY / WATCH / NO_TRADE) is determined by both the score and a set of hard gate conditions.

The function is called automatically inside `analyze_ticker()` and appended to every `/analyze/{ticker}` response as the `swing_setup` field.

---

## The Seven Conditions

### 1. Uptrend Confirmed (hard gate)

```
price > SMA 50  AND  price > SMA 200  AND  SMA 50 > SMA 200
```

All three must be true simultaneously. This ensures the stock is in a genuine intermediate and long-term uptrend, not just a short-term bounce. The values are reused from `compute_trend_signals()` — no recomputation.

**Why all three?**
`price > SMA 200` alone can trigger in a dead-cat bounce. Requiring `SMA 50 > SMA 200` (a classic "golden cross" alignment) ensures the medium-term trend has crossed above the long-term trend as well.

---

### 2. ADX ≥ 20 (trend strength)

```
talib.ADX(high, low, close, timeperiod=14)[-1]
```

ADX (Average Directional Index) measures trend *strength*, not direction. A weak trend (ADX < 20) means the pullback entry has a poor base to recover from.

ADX is the only indicator computed fresh inside `compute_swing_setup_pullback` — it is not needed by any other analysis stage, so it is scoped locally rather than added to the shared pipeline.

| ADX value | Points awarded |
|---|---|
| ≥ 25 | 10 |
| 20 – 24 | 7 |
| 15 – 19 | 4 (partial credit) |
| < 15 | 0 |

---

### 3. RSI 40 – 62 (pullback zone)

```
RSI(14) from compute_momentum_signals()
```

The RSI window defines "healthy pullback" territory:

- **> 62** — momentum is still extended, not a clean pullback yet
- **40 – 62** — price has cooled off from overbought levels; ideal entry zone
- **< 40** — momentum collapse, not a pullback — more likely a trend reversal or breakdown

The 14-period RSI value is reused directly from `momentum["rsi"]`.

---

### 4. Near Support (location filter)

The price must be sitting close to a known support level. Two methods are checked; passing either is sufficient:

**ATR-based (primary):**
```
abs(price - nearest_support) ≤ 0.75 × ATR(14)
```
If price is within three-quarters of one average daily range from the support level, it is considered "at support." This scales automatically with the stock's volatility.

**Percentage fallback:**
```
distance_to_support_pct < 3.0%
```
Used when ATR is unavailable or as a secondary confirmation.

`nearest_support` comes from `compute_support_resistance()` — the closest swing low below price (from the last 90 trading days, using `scipy.signal.argrelextrema` with `order=5`) or the 52-week low as a fallback.

---

### 5. Volume Declining

```
volume_ratio = current_volume / avg_volume_20d  (from compute_volume_signals)
volume_declining = volume_ratio < 1.0
```

Healthy pullbacks retrace on *lower* volume than the prior trend moves. High volume during the pullback suggests distribution (institutional selling), not a pause.

**OBV bonus:** If `obv_trend == "RISING"`, the On-Balance Volume is still accumulating even as price pulls back — a bullish divergence that adds points.

| Condition | Points |
|---|---|
| OBV trend is RISING | +6 |
| Volume declining (ratio < 1.0) | +4 |
| Volume elevated on pullback (ratio > 1.3) | −3 (penalty) |

---

### 6. Reversal Candle (candlestick confirmation)

A dedicated helper `_find_reversal_candles(df, scan_bars=5)` scans the last 5 bars for any bullish pattern from an allowlist of 8 TA-Lib functions:

| TA-Lib name | Pattern |
|---|---|
| `CDLENGULFING` | Bullish engulfing |
| `CDLHAMMER` | Hammer |
| `CDLINVERTEDHAMMER` | Inverted hammer |
| `CDLPIERCING` | Piercing line |
| `CDLMORNINGSTAR` | Morning star |
| `CDLMORNINGDOJISTAR` | Morning doji star |
| `CDLHARAMI` | Bullish harami |
| `CDLHARAMICROSS` | Harami cross |

For each pattern, only the *most recent* bullish occurrence in the 5-bar window is recorded, along with:
- `bars_ago` — 0 = today, 1 = yesterday, etc.
- `raw_value` — TA-Lib integer value (100 = normal, 200 = strong)
- `strength` — `"strong"` if `raw_value ≥ 200`, else `"normal"`

Results are sorted newest-first, then strongest-first.

**Points:**

| Most recent pattern age | Points |
|---|---|
| ≤ 2 bars ago | 15 |
| 3 – 4 bars ago | 8 |
| Not found | 0 |

---

### 7. Trigger — Break of Prior Day High

```
close[-1] > high[-2]
```

Even with all other conditions in place, an entry is held back until price *proves* intent by closing above the prior day's high. This is the simplest momentum-confirmation trigger — a single-bar breakout of the most recent resistance level.

**Worth 10 points.** It is also a *hard gate* for the ENTRY verdict (see below).

---

## Scoring

All components are summed and clamped to 0–100:

| Component | Max points |
|---|---|
| Uptrend confirmed | 30 |
| ADX strength | 10 |
| Pullback quality (RSI + near support) | 25 |
| Volume / OBV | 10 |
| Reversal candle | 15 |
| Trigger | 10 |
| **Total** | **100** |

Pullback quality awards the full 25 points only when *both* `rsi_ok` and `near_support` are true. Either alone scores 12.

---

## Verdict Rules

Verdicts are not purely score-based — score is a necessary but not sufficient condition.

### ENTRY
All four hard gates must be true **and** score ≥ 70:

```
uptrend_confirmed  = True
near_support       = True
reversal_found     = True   (any pattern in last 5 bars)
trigger_ok         = True   (close > prior day high)
setup_score        ≥ 70
```

### WATCH
A setup that is forming but not yet confirmed. Score ≥ 55 plus:

```
uptrend_confirmed  = True
near_support OR rsi_ok                 (at least one pullback quality condition met)
reversal_found OR price in entry_zone  (candle or price location)
```

### NO_TRADE
Anything that does not meet ENTRY or WATCH criteria — most commonly because `uptrend_confirmed` is false (downtrend or sideways market).

---

## Risk Level Calculations

All risk levels are ATR-anchored so they scale with each stock's volatility.

```
entry_zone_low  = nearest_support − 0.5 × ATR
entry_zone_high = nearest_support + 0.5 × ATR
stop_loss       = nearest_support − 1.0 × ATR
target          = nearest_resistance           (or price + 2 × (price − stop) if no resistance)
R:R             = (nearest_resistance − price) / (price − stop_loss)
```

If `nearest_support` is unavailable (falls back to 0), the entry zone and stop are anchored to current price instead:
```
entry_zone      = price ± 0.5 × ATR
stop_loss       = price − 1.5 × ATR
```

---

## S/R Alignment

A qualitative summary of where price sits relative to key levels:

| Value | Meaning |
|---|---|
| `aligned` | Price is near support — good entry location |
| `misaligned` | Price is near resistance — poor risk/reward |
| `neutral` | Price is between levels |

---

## Data Flow

```
GET /analyze/{ticker}
  └─ analyze_ticker(df, symbol, price)
       ├─ compute_trend_signals(df)          → trend dict
       ├─ compute_momentum_signals(df)       → momentum dict
       ├─ compute_volatility_signals(df)     → volatility dict
       ├─ compute_volume_signals(df)         → volume dict
       ├─ compute_support_resistance(df)     → sr dict
       ├─ compute_candlestick_patterns(df, sr)
       └─ compute_swing_setup_pullback(      ← reuses all dicts above
              df, trend, momentum,
              volatility, volume, sr
          )  → swing_setup dict
```

`compute_swing_setup_pullback` reads from the already-computed dicts and only adds one new computation (ADX via TA-Lib). It is wrapped in `try/except` so a failure never breaks the rest of the analysis.

---

## Limitations (v1)

- **Daily bars only.** No weekly trend confirmation. A stock could be in a daily uptrend but a weekly downtrend.
- **No sector/market context.** A pullback during a broad market sell-off scores the same as one in a strong tape.
- **Single setup type.** Only "pullback in uptrend" is detected. Breakouts, reversals, and mean-reversion setups are not covered.
- **Support accuracy.** `nearest_support` uses `argrelextrema` with `order=5` on a 90-day lookback. Very recent swing lows (fewer than 5 bars confirmed) will not be detected and the level falls back to the 52-week low, which may be far away.
- **No position sizing.** Risk levels are computed but no lot size or dollar-risk is suggested.
