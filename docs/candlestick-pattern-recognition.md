# Candlestick Pattern Recognition — TA-Lib Integration

How the trading copilot detects candlestick patterns, what data it uses, and how results are interpreted.

---

## Overview

Pattern recognition is the final stage of the TA pipeline. It runs after trend, momentum, volatility, volume, and support/resistance signals have all been computed. The output is a list of patterns that fired on the **most recent bar**, enriched with an S/R proximity significance rating.

Entry point: `app/services/ta_engine.py → compute_candlestick_patterns()`

---

## Data fed to TA-Lib

`analyze_ticker()` receives the **full price history** from the database — `HISTORY_PERIOD = "6y"` means roughly **1,500 trading-day bars** for an actively traded stock.

```python
# app/routers/analysis.py
ticker_info, price_list, source = get_or_refresh_data(ticker)  # no day limit
df = _prepare_dataframe(price_list)                             # all ~1,500 rows
result = analyze_ticker(df, ticker_info["symbol"], float(price))
```

Inside `compute_candlestick_patterns`, the full OHLC history is converted to NumPy arrays and passed to every pattern function:

```python
# app/services/ta_engine.py
o = df["open"].values   # shape: (~1500,)
h = df["high"].values
l = df["low"].values
c = df["close"].values

result = func(o, h, l, c)   # TA-Lib ingests the full history
last_val = int(result[-1])  # only the final element is checked
```

**Why the full history?** TA-Lib is a C library that computes the indicator over the entire input array. Multi-bar patterns (e.g., Morning Star is 3 bars, Rising/Falling Three Methods is 5 bars) need surrounding context to identify the pattern correctly. Feeding fewer bars would risk incorrect lookback alignment. TA-Lib ignores the extra history — it's cheap to pass.

---

## Pattern detection loop

TA-Lib exposes **61 pattern recognition functions**, all prefixed with `CDL`. The engine iterates over every one:

```python
candle_funcs = talib.get_function_groups()["Pattern Recognition"]
# Returns all 61 CDL* function names as strings

patterns = []
for func_name in candle_funcs:
    func = getattr(talib, func_name)   # e.g. talib.CDLENGULFING
    result = func(o, h, l, c)          # integer array, same length as input
    last_val = int(result[-1])
    if last_val != 0:
        pattern_name = func_name.replace("CDL", "").lower()   # "engulfing"
        pattern_type = "bullish" if last_val > 0 else "bearish"
        patterns.append({ ... })
```

### Return value semantics

TA-Lib pattern functions return an integer array with three possible values at each index:

| Value | Meaning |
|-------|---------|
| `+100` | Bullish pattern completed at this bar |
| `-100` | Bearish pattern completed at this bar |
| `0`    | No pattern at this bar |

Some patterns use `+200` / `-200` for varying strength (e.g., `CDLMORNINGSTAR` with a doji vs. plain morning star). These are still treated as bullish/bearish in the current implementation since the sign is all that matters.

---

## Significance rating

Every detected pattern is rated `HIGH` or `LOW` based on whether the current price is within 2% of the nearest support or resistance level:

```python
nearest_support    = support_resistance.get("nearest_support", 0)
nearest_resistance = support_resistance.get("nearest_resistance", 0)

at_support    = abs(price - nearest_support)    / price * 100 < 2  if nearest_support    else False
at_resistance = abs(price - nearest_resistance) / price * 100 < 2  if nearest_resistance else False
significance  = "HIGH" if (at_support or at_resistance) else "LOW"
```

This is computed once and applied to **all** patterns found on that bar — they all share the same price context.

---

## All 61 patterns scanned

| Pattern | Type hint | Notes |
|---------|-----------|-------|
| `CDL2CROWS` | Bearish | 3-bar reversal at top |
| `CDL3BLACKCROWS` | Bearish | Strong downtrend continuation |
| `CDL3INSIDE` | Reversal | Harami + confirmation |
| `CDL3LINESTRIKE` | Continuation | Counter-move swallowed |
| `CDL3OUTSIDE` | Reversal | Engulfing + confirmation |
| `CDL3STARSINSOUTH` | Bullish | Rare 3-bar reversal |
| `CDL3WHITESOLDIERS` | Bullish | Strong uptrend continuation |
| `CDLABANDONEDBABY` | Reversal | Doji gap pattern; very rare |
| `CDLADVANCEBLOCK` | Bearish | Weakening uptrend |
| `CDLBELTHOLD` | Reversal | Single bar, open = extreme |
| `CDLBREAKAWAY` | Reversal | 5-bar gap reversal |
| `CDLCLOSINGMARUBOZU` | Trend | Close at extreme of range |
| `CDLCONCEALBABYSWALL` | Bullish | Rare 4-bar reversal |
| `CDLCOUNTERATTACK` | Reversal | Two-bar same-close |
| `CDLDARKCLOUDCOVER` | Bearish | 2-bar reversal; close > 50% inside |
| `CDLDOJI` | Neutral | Indecision; open ≈ close |
| `CDLDOJISTAR` | Reversal | Doji after long candle |
| `CDLDRAGONFLYDOJI` | Bullish | Long lower shadow, no body |
| `CDLENGULFING` | Reversal | 2-bar; body engulfs prior bar |
| `CDLEVENINGDOJISTAR` | Bearish | Doji variant of evening star |
| `CDLEVENINGSTAR` | Bearish | 3-bar top reversal |
| `CDLGAPSIDESIDEWHITE` | Continuation | Gap + 2 same-side white bars |
| `CDLGRAVESTONEDOJI` | Bearish | Long upper shadow, no body |
| `CDLHAMMER` | Bullish | Small body, long lower shadow in downtrend |
| `CDLHANGINGMAN` | Bearish | Same shape as hammer but in uptrend |
| `CDLHARAMI` | Reversal | Inside bar (body contained) |
| `CDLHARAMICROSS` | Reversal | Harami where 2nd bar is a doji |
| `CDLHIGHWAVE` | Indecision | Very long shadows both sides |
| `CDLHIKKAKE` | Reversal | Inside bar trap pattern |
| `CDLHIKKAKEMOD` | Reversal | Modified hikkake |
| `CDLHOMINGPIGEON` | Bullish | 2-bar inside in downtrend |
| `CDLIDENTICAL3CROWS` | Bearish | 3 equal-open black candles |
| `CDLINNECK` | Bearish | 2-bar; close at prior low |
| `CDLINVERTEDHAMMER` | Bullish | Inverted hammer in downtrend |
| `CDLKICKING` | Strong reversal | 2 marubozus; gap between |
| `CDLKICKINGBYLENGTH` | Strong reversal | Kicking, weighted by length |
| `CDLLADDERBOTTOM` | Bullish | 5-bar reversal with inverted hammer |
| `CDLLONGLEGGEDDOJI` | Indecision | Doji with very long shadows |
| `CDLLONGLINE` | Trend | Long-bodied candle |
| `CDLMARUBOZU` | Trend | No wicks; open = low or high |
| `CDLMATCHINGLOW` | Bullish | Two bars close at same low |
| `CDLMATHOLD` | Continuation | Bullish mat hold |
| `CDLMORNINGDOJISTAR` | Bullish | Doji variant of morning star |
| `CDLMORNINGSTAR` | Bullish | 3-bar bottom reversal |
| `CDLONNECK` | Bearish | 2-bar; close at prior low |
| `CDLPIERCING` | Bullish | 2-bar; close > 50% inside prior |
| `CDLRICKSHAWMAN` | Indecision | Long-legged doji, centered body |
| `CDLRISEFALL3METHODS` | Continuation | 5-bar with 3-bar retracement |
| `CDLSEPARATINGLINES` | Continuation | Gap open, same direction |
| `CDLSHOOTINGSTAR` | Bearish | Small body, long upper shadow in uptrend |
| `CDLSHORTLINE` | Indecision | Small-range candle |
| `CDLSPINNINGTOP` | Indecision | Small body, balanced shadows |
| `CDLSTALLEDPATTERN` | Bearish | 3 white soldiers stalling |
| `CDLSTICKSANDWICH` | Bullish | 2 same-close bars around a gap |
| `CDLTAKURI` | Bullish | Dragonfly doji in downtrend |
| `CDLTASUKIGAP` | Continuation | 3-bar gap continuation |
| `CDLTHRUSTING` | Bearish | 2-bar; close does not pierce midpoint |
| `CDLTRISTAR` | Reversal | 3 dojis |
| `CDLUNIQUE3RIVER` | Bullish | Rare 3-bar reversal |
| `CDLUPSIDEGAP2CROWS` | Bearish | Gap up, then 2 black candles |
| `CDLXSIDEGAP3METHODS` | Continuation | 3-bar gap continuation |

---

## Output structure

`compute_candlestick_patterns` returns a list of dicts — one per detected pattern:

```python
[
  {
    "pattern":        "engulfing",   # CDL prefix stripped, lowercased
    "pattern_type":   "bullish",     # or "bearish"
    "at_support":     True,          # price within 2% of nearest support
    "at_resistance":  False,
    "significance":   "HIGH",        # HIGH if at_support or at_resistance
  },
  ...
]
```

If no patterns fired on the last bar, the list is empty (`[]`).

---

## Example: detecting a Bullish Engulfing

Given a 1,500-bar array, TA-Lib computes `CDLENGULFING` over all bars and returns an array of the same length. Only the last element is read:

```python
result = talib.CDLENGULFING(o, h, l, c)
# result[-1] == 100   → bullish engulfing on today's bar
# result[-1] == -100  → bearish engulfing on today's bar
# result[-1] == 0     → no engulfing pattern today
```

The pattern fires when:
- Bar N-1: bearish candle (close < open)
- Bar N (today): bullish candle whose body fully engulfs bar N-1's body (open ≤ prev_close AND close ≥ prev_open)

---

## Significance in context

A Bullish Engulfing at a key support level (significance = HIGH) is a meaningfully stronger signal than the same pattern in mid-range. The frontend `SignalPanel` can use the `significance` field to visually distinguish high-confidence patterns.

Support/resistance levels come from `compute_support_resistance()`, which derives them from:
- 52-week high/low (252 trading days)
- Swing highs/lows within the last 90 days (via `scipy.signal.argrelextrema`, order=5)

---

## Limitations

- **Last-bar only**: patterns are evaluated only on the current/most-recent candle. Historical pattern occurrences are not returned.
- **Significance is binary**: all patterns on a bar share the same `HIGH`/`LOW` rating based on the single nearest S/R level.
- **No volume filter**: TA-Lib pattern functions use only OHLC; volume confirmation (e.g., higher volume on engulfing day) is not checked.
- **Return value granularity**: `+200`/`-200` strength variants from TA-Lib are collapsed to `bullish`/`bearish` — strength gradation is not exposed.
