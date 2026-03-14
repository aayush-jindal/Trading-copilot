## 1. Session Overview

This development session focused on **auditing and improving the swing trading detection system** in the Trading Copilot platform, across both backend analytics and frontend presentation.

**Improved areas (6 primary themes):**

- **Data pipeline & history length** feeding the TA engine.
- **Support/Resistance detection and strength scoring.**
- **Weekly trend confirmation and integration into swing setups.**
- **RSI pullback (cooldown) logic and scoring.**
- **Trigger bar logic for breakouts, including volume and bar-strength confirmation.**
- **Verdict logic for `ENTRY` vs `WATCH` vs `NO_TRADE`, plus candlestick pattern display.**

Additional UI/UX refinements and testing improvements were made in support of these core changes.

---

## 2. Fix 1 — Data Pipeline Audit

### Problem

- There was a risk that **`get_latest_prices()`** (or other “N‑day slice” calls) might be used to feed the TA engine, which would:
  - Truncate history **before** computing indicators.
  - Potentially undercut signals that require long lookbacks (e.g. **SMA 200**, BB squeeze).

### Audit

All **four** call sites that invoke the TA engine entrypoint `analyze_ticker` were audited:

- `app/routers/analysis.py`
- `app/routers/synthesis.py`
- `app/routers/watchlist.py`
- `app/services/digest.py`

Each was checked to ensure that:

- They call **`get_or_refresh_data(ticker)`**, not any “latest N bars” helper.
- The full available daily history is passed into `_prepare_dataframe(...)` → `analyze_ticker(...)`.

### Fix: Minimum Bar Threshold in `analyze_ticker`

Previously, `analyze_ticker` only required **50 bars**. This was raised to **200 bars**:

```python
if len(df) < 200:
    raise ValueError(
        f"Insufficient data for {symbol}: need at least 200 bars, got {len(df)}"
    )
```

**Rationale:**

- **SMA 200** logically requires 200 points of data to be meaningful.
- **BB squeeze** requires:
  - A 20‑bar Bollinger Band window.
  - A 120‑bar history of BB widths to compute the 20th percentile.
  - Combined, this implies **≥ 140 bars** at minimum; 200 bars is a safer floor.

### Fix: `compute_support_resistance` Signature

For API clarity and future flexibility, the S/R routine was parameterised:

```python
def compute_support_resistance(df: pd.DataFrame, swing_lookback: int = 90) -> dict:
    ...
```

- The `swing_lookback` parameter is now **explicit** and documented as retained for compatibility.
- The implementation internally ignores this parameter (using fixed 90/252/504 windows), but call sites remain backward compatible.

### Audit Result: Call-Site Table

All `analyze_ticker` call sites were confirmed to use **full-history** data via `get_or_refresh_data`:

| Location                  | Data Source                | History Length Passed to TA Engine           |
|---------------------------|----------------------------|----------------------------------------------|
| `analysis.py`            | `get_or_refresh_data`      | Full daily history                           |
| `synthesis.py`           | `get_or_refresh_data`      | Full daily history                           |
| `watchlist.py`           | `get_or_refresh_data`      | Full daily history                           |
| `digest.py`              | `get_or_refresh_data`      | Full daily history                           |

No call site was found to rely on `get_latest_prices()` or any equivalent sliced source.

---

## 3. Fix 2 — Support/Resistance Overhaul

### Problem

- Original implementation:
  - Used a **single 90‑day lookback** with `argrelextrema(order=5)`.
  - Treated every swing level **equally** (no touch-based strength).
  - 90 days is too short to capture **1–2 year historical levels** that often matter for swing trading.
  - Some **below‑price highs** were showing up in resistance lists due to overly loose filtering.

### Multi-Window Swing Detection

The new implementation in `compute_support_resistance` uses **three windows** in parallel:

```python
_WINDOWS: list[tuple[int, int]] = [
    (90,  3),   # recent structure — last ~4 months, sensitive detection
    (252, 5),   # 1-year major levels — filters out noise
    (504, 8),   # 2-year significant levels — only major turning points
]
```

For each `(window_days, order)` pair:

- Slice the last `window_days` bars.
- Run `argrelextrema` on `high` (for swing highs) and `low` (for swing lows).
- Accumulate all detected levels into `raw_highs` and `raw_lows`.

### Clustering Within 1% Band

Nearby levels are merged within a **±1% band**:

```python
def _cluster(levels: list[float], tol_pct: float = 1.0) -> list[float]:
    if not levels:
        return []
    clusters: list[list[float]] = [[sorted(levels)[0]]]
    for lvl in sorted(levels)[1:]:
        anchor = clusters[-1][0]
        if abs(lvl - anchor) / anchor * 100 <= tol_pct:
            clusters[-1].append(lvl)
        else:
            clusters.append([lvl])
    return [sum(c) / len(c) for c in clusters]
```

This prevents over-counting multiple nearby highs/lows that are effectively the **same level**.

### Touch-Count Strength Scoring

Each clustered level is scored by **touch count**:

```python
def _score(level: float) -> tuple[int, str]:
    band_lo = level * 0.995
    band_hi = level * 1.005
    touches = int(np.sum((high_vals >= band_lo) & (low_vals <= band_hi)))
    if touches >= 3:
        return 3, "HIGH"
    if touches >= 2:
        return 2, "MEDIUM"
    return 1, "LOW"
```

- **3+ touches** → `HIGH` strength.
- **2 touches** → `MEDIUM`.
- **1 touch** → `LOW`.

### New Output Fields

`compute_support_resistance` now returns:

- `support_strength: "HIGH" | "MEDIUM" | "LOW"`
- `resistance_strength: "HIGH" | "MEDIUM" | "LOW"`
- `swing_highs: list[{"price": float, "strength": str}]`
- `swing_lows: list[{"price": float, "strength": str}]`

Each element in `swing_highs` / `swing_lows` is a dict with:

- `price`: clustered level price (rounded to 2 decimals).
- `strength`: strength label derived from touch count.

### Directional Filtering Bug Fix

To avoid below‑price highs being misclassified as resistance (and vice versa), stricter filters were applied:

- **Resistance** candidates: `p > current_price`.
- **Support** candidates: `p < current_price`.

These rules are enforced consistently for:

- Nearest resistance/support selection.
- `swing_highs` and `swing_lows` lists.

### Frontend Changes

Support/resistance detail is surfaced via:

- Strength badges (e.g. **HIGH**, **MEDIUM**, **LOW**) on:
  - Nearest support and resistance.
  - Swing setup panel conditions (support row).
- Swing level lists that show:
  - Price levels and their strength.
  - Nearest levels highlighted in the swing setup risk panel.

---

## 4. Fix 3 — Weekly Trend Confirmation

### Problem

- The system previously used only **daily charts**, with no protection against:
  - Entering a **daily uptrend** while the **weekly trend is down**.
  - This can lead to taking pullbacks **against** the higher‑timeframe trend.

### New Database Table

- **`weekly_price_history`**:
  - Same schema as `price_history`.
  - Stores 1‑week OHLCV bars, typically **2 years** of data.

### New Data Function

`fetch_weekly_data(symbol)`:

- Uses `ticker.history(period="2y", interval="1wk")`.
- Produces a list of weekly OHLCV dicts.
- Integrated into `fetch_ticker_data` and stored in `weekly_price_history`.
- Called **best-effort**; failures are caught and handled gracefully.

### Weekly Trend TA Function

`compute_weekly_trend(weekly_df: pd.DataFrame) -> dict`:

- Requires **≥ 42 weekly bars** (SMA40 + 2‑bar safety buffer).
- Computes:

```python
sma10_series = SMAIndicator(close, window=10).sma_indicator()
sma40_series = SMAIndicator(close, window=40).sma_indicator()
...
weekly_trend = "BULLISH" | "BEARISH" | "NEUTRAL"
weekly_trend_strength = "STRONG" | "MODERATE" | "WEAK"
```

**Trend rules:**

- **BULLISH**: `price > SMA10 > SMA40`.
- **BEARISH**: `price < SMA10 < SMA40`.
- **NEUTRAL**: any mixed configuration.

### Integration into Swing Setup

`compute_swing_setup_pullback` accepts an optional `weekly_trend` dict:

- `weekly_trend_aligned: bool`:
  - `True` when weekly trend is **BULLISH**.
  - `False` when weekly trend is anything else.
  - `True` by default when weekly data is missing (`None` → treated as aligned to avoid penalising older callers).
- **Hard gate**:

```python
if not weekly_trend_aligned and verdict == "ENTRY":
    verdict = "WATCH"
    weekly_trend_warning = (
        "Daily setup forming against weekly trend — reduced conviction"
    )
```

**New output fields:**

- `conditions.weekly_trend_aligned: bool`
- `weekly_trend_warning: Optional[str]`
- `weekly_trend` object added to the top-level analysis response.

### Frontend Changes

- Trend card shows:
  - Daily trend signal.
  - Weekly trend badge, e.g. `W · BULLISH STRONG`.
- Swing setup panel:
  - New condition row: **“Weekly trend aligned”**.
  - When the weekly gate downgrades an `ENTRY` to `WATCH`, an **amber warning line** appears with `weekly_trend_warning`.

### Fallback Behavior

- `_NEUTRAL_WEEKLY_TREND` constant is used when:
  - Weekly data is missing.
  - Weekly computation fails (wrapped in `try/except`).
- In these cases, swing setup treats weekly alignment as **not penalising** (aligned by definition when weekly_trend is `None`).

---

## 5. Fix 4 — RSI Cooldown Logic

### Problem

- Original pullback detection used a **hard-coded RSI band**, e.g. 40–62:
  - Treated all tickers identically, regardless of volatility, trend persistence, or “RSI personality”.
  - Could misclassify shallow pullbacks in strong trends as “no pullback”, or moderate reversion as too strong/too weak.

### Cooldown-From-Peak Implementation

Inside `compute_swing_setup_pullback`:

```python
_rsi_series = RSIIndicator(df["close"], window=14).rsi()
_rsi_peak_raw = _rsi_series.iloc[-20:].max()
rsi_peak: float = float(_rsi_peak_raw) if pd.notna(_rsi_peak_raw) else rsi
rsi_cooldown: float = round(rsi_peak - rsi, 1)
```

- `rsi_peak` is the **max RSI over the last 20 bars**.
- `rsi_cooldown = rsi_peak - current_rsi` measures how far momentum has cooled from the recent overbought area.

### Scoring Thresholds

```python
if rsi < 35 or rsi > 70:
    rsi_ok, rsi_label = False, "no_pullback"
elif rsi_cooldown >= 15:
    rsi_ok, rsi_label = True, "healthy_pullback"
elif rsi_cooldown >= 8:
    rsi_ok, rsi_label = True, "moderate_pullback"
elif rsi_cooldown >= 3:
    rsi_ok, rsi_label = True, "mild_pullback"
else:
    rsi_ok, rsi_label = False, "no_pullback"
```

- **Safety floor**: `RSI < 35` → `no_pullback` (momentum collapse).
- **Ceiling**: `RSI > 70` → `no_pullback` (still overbought).

**Scoring:**

- `healthy_pullback` or `moderate_pullback` → **13 points**.
- `mild_pullback` → **6 points**.
- `no_pullback` → **0 points**.

These points are combined with **near support** (12 points) to form the **25‑point pullback bucket**.

### New Output Fields

In `conditions`:

- `rsi_cooldown: float`
- `rsi_pullback_label: str` (`"healthy_pullback"`, `"moderate_pullback"`, `"mild_pullback"`, `"no_pullback"`)
- `pullback_rsi_ok: bool`

### Frontend Changes

- The RSI condition row now shows:
  - Label: **“RSI cooled Xpts from peak”**.
  - Detail: humanised label (`healthy pullback`, `moderate pullback`, etc.).
  - Pass/fail: based on `pullback_rsi_ok`.

This replaces the older **“40–62 band”** messaging.

### Implementation Note

- RSI is **recomputed locally** inside `compute_swing_setup_pullback`:

```python
_rsi_series = RSIIndicator(df["close"], window=14).rsi()
```

- This avoids threading RSI series through multiple layers and keeps the cooldown logic self-contained and testable.

---

## 6. Fix 5 — Trigger Bar Logic

### Problem

- Original trigger:

```python
trigger_ok = price > prev_high  # close[-1] > high[-2]
```

- Limitations:
  - Watched only **yesterday’s high**, ignoring multi-bar consolidations.
  - No **volume** confirmation.
  - No **bar strength** (close location in range) confirmation.
  - Binary 10‑point contribution in the score.

### 3-Bar Breakout Logic

```python
three_bar_high = float(df["high"].iloc[-4:-1].max())
trigger_price: float = three_bar_high

price_trigger: bool = bool(price > three_bar_high)
```

- Uses the **highest high of the last 3 completed bars** (prior to today).
- Captures multi-bar consolidation breakouts more robustly.

### Volume Confirmation

```python
current_volume: float = float(volume.get("current_volume") or 0.0)
avg_volume_20d: float = float(volume.get("avg_volume_20d") or 0.0)
trigger_volume_ok: bool = bool(
    avg_volume_20d > 0.0 and current_volume >= avg_volume_20d
)
```

- Requires volume **≥ 20‑day average** to treat the breakout as properly sponsored.

### Bar Strength Confirmation

```python
bar_high = float(df["high"].iloc[-1])
bar_low = float(df["low"].iloc[-1])
bar_range = bar_high - bar_low

if bar_range > 0:
    trigger_bar_strength_ok = bool((price - bar_low) / bar_range > 0.5)
else:
    trigger_bar_strength_ok = False
```

- Confirms that the close is in the **upper half** of the bar range.
- **Doji guard**: when `bar_range == 0`, `trigger_bar_strength_ok` is forced to `False` to avoid division by zero.

### Tiered Scoring & Labels

```python
if price_trigger:
    trigger_ok = True
    if trigger_volume_ok and trigger_bar_strength_ok:
        trigger_points = 10
        trigger_label = "strong"
    elif trigger_volume_ok or trigger_bar_strength_ok:
        trigger_points = 7
        trigger_label = "moderate"
    else:
        trigger_points = 4
        trigger_label = "weak"
else:
    trigger_ok = False
    trigger_points = 0
    trigger_label = "not_fired"

score += trigger_points
```

- **All three true** → `10` points, `trigger_label = "strong"`.
- **Price + one confirm** → `7` points, `"moderate"`.
- **Price only** → `4` points, `"weak"`.
- **No price trigger** → `0` points, `"not_fired"`.

**ENTRY hard gate:**

- **Unchanged** — `ENTRY` still requires `trigger_ok = True` in addition to other conditions.

### New Output Fields

In `conditions`:

- `trigger_ok: bool`
- `trigger_price: float` (the `three_bar_high` value)
- `trigger_volume_ok: bool`
- `trigger_bar_strength_ok: bool`
- `trigger_points: int` (0, 4, 7, or 10)
- `trigger_label: "strong" | "moderate" | "weak" | "not_fired"`

### Frontend Changes

- **When not fired:**
  - Label: `Trigger — close above $XXX.XX`, using `trigger_price`.
  - Detail: `"waiting for breakout"`.
- **When fired:**
  - Label: `Trigger fired · strong/moderate/weak` (mapped via a local label map with fallback to `"weak"`).
  - Detail: combination of:
    - `vol ≥ 20d avg` vs `vol < 20d avg`.
    - `close in upper half` vs `weak close location`.

### Bug Fix: “Trigger fired · undefined”

- Root cause: `trigger_label` previously passed directly into the label text with no sanity mapping.
- Fix:
  - Introduced `TRIGGER_LABEL_MAP` in `SwingSetupPanel`.
  - Handles all four labels explicitly (`strong`, `moderate`, `weak`, `not_fired`).
  - Any unexpected value falls back to `"weak"`.

---

## 7. Fix 6 — WATCH Verdict Logic Correction

### Problem

- Old WATCH condition:

```python
elif (
    uptrend_confirmed
    and (near_support or rsi_ok)
    and (reversal_found or in_entry_zone)
    and score >= 55
):
    verdict = "WATCH"
```

- This **incorrectly required**:
  - Either a confirmed **reversal candle**, or
  - Being **inside** the entry zone.
- As a result, some high-score setups with:
  - Confirmed uptrend,
  - Strong pullback and support alignment,
  - But **no reversal candle yet**,
  - Were downgraded to `NO_TRADE`.

### Fix

- The `(reversal_found or in_entry_zone)` gate was **removed** from the WATCH criteria:

```python
elif (
    uptrend_confirmed
    and (near_support or rsi_ok)
    and score >= 55
):
    verdict = "WATCH"
```

### Current Conditions

- **ENTRY** (unchanged):
  - `uptrend_confirmed`
  - `near_support`
  - `reversal_found`
  - `trigger_ok`
  - `score >= 70`

- **WATCH** (corrected):
  - `uptrend_confirmed`
  - `(near_support OR rsi_ok)`
  - `score >= 55`

**Impact example:**

- A ticker like **XLE** with:
  - Strong uptrend,
  - At or near support,
  - RSI in healthy pullback range,
  - No reversal candle or trigger yet,
  - Score around 75,
  - Now correctly yields **`WATCH`** rather than `NO_TRADE`.

---

## 8. Fix 7 — Candlestick Pattern Display Names

### Problem

- TA‑Lib candlestick patterns were exposed as raw stripped names:
  - `"belthold"`, `"longline"`, `"separatinglines"`, `"invertedhammer"`, etc.
  - Not suitable for direct display in the UI.

### Pattern Name Mapping

Inside `compute_candlestick_patterns`, a `PATTERN_NAMES` dict was added:

```python
PATTERN_NAMES: dict[str, str] = {
    "belthold": "Belt Hold",
    "longline": "Long Line",
    "separatinglines": "Separating Lines",
    "invertedhammer": "Inverted Hammer",
    "hammer": "Hammer",
    "engulfing": "Engulfing",
    "morningstar": "Morning Star",
    "eveningstar": "Evening Star",
    "morningdojistar": "Morning Doji Star",
    "eveningdojistar": "Evening Doji Star",
    "shootingstar": "Shooting Star",
    "doji": "Doji",
    "dojistar": "Doji Star",
    "dragonflydoji": "Dragonfly Doji",
    "gravestonedoji": "Gravestone Doji",
    "harami": "Harami",
    "haramicross": "Harami Cross",
    "piercing": "Piercing Line",
    "darkcloudcover": "Dark Cloud Cover",
    "threewhitesoldiers": "Three White Soldiers",
    "threeblackcrows": "Three Black Crows",
    "risingthreemethods": "Rising Three Methods",
    "fallingthreemethods": "Falling Three Methods",
    "marubozu": "Marubozu",
    "spinningtop": "Spinning Top",
    "highwave": "High Wave",
    "rickshawman": "Rickshaw Man",
    "longleggeddoji": "Long Legged Doji",
    "takuri": "Takuri",
    "tristar": "Tri-Star",
    "abandonedbaby": "Abandoned Baby",
    "breakaway": "Breakaway",
    "concealbabyswall": "Concealing Baby Swallow",
    "counterattack": "Counterattack",
    "gapsidesidewhite": "Gap Side-by-Side White",
    "hikkake": "Hikkake",
    "hikkakemod": "Modified Hikkake",
    "homingpigeon": "Homing Pigeon",
    "identical3crows": "Identical Three Crows",
    "inneck": "In-Neck",
    "kicking": "Kicking",
    "kickingbylength": "Kicking By Length",
    "ladderbottom": "Ladder Bottom",
    "matchinglow": "Matching Low",
    "onneck": "On-Neck",
    "stalledpattern": "Stalled Pattern",
    "sticksandwich": "Stick Sandwich",
    "tasukigap": "Tasuki Gap",
    "thrusting": "Thrusting",
    "upsidegap2crows": "Upside Gap Two Crows",
    "xsidegap3methods": "Upside/Downside Gap Three Methods",
    "2crows": "Two Crows",
    "3inside": "Three Inside Up/Down",
    "3linestrike": "Three Line Strike",
    "3outside": "Three Outside Up/Down",
    "3starsinsouth": "Three Stars In The South",
    "3blackcrows": "Three Black Crows",
    "3whitesoldiers": "Three White Soldiers",
}
```

### Fallback for Unmapped Patterns

When iterating over TA‑Lib pattern functions:

```python
raw_name = func_name.replace("CDL", "").lower()
display_name = PATTERN_NAMES.get(
    raw_name,
    raw_name.replace("_", " ").title(),
)
...
patterns.append({
    "pattern": display_name,
    ...
})
```

- If `raw_name` is present in `PATTERN_NAMES`, its mapped display name is used.
- Otherwise, a reasonable default is constructed:
  - Replace `_` with space.
  - `.title()` to get capitalisation (e.g. `"three_inside"` → `"Three Inside"`).

Result: **no raw lowercase strings** ever reach the frontend.

---

## 9. Testing Coverage Added

This session added or reinforced tests across the stack:

### Data Pipeline / S.R. / Trend

- Verified `compute_support_resistance`:
  - All **swing highs > price** and **swing lows < price**.
  - Nearest support/resistance obey directional invariants (`support < price < resistance`).
  - Swing highs/lows lists are sorted correctly (nearest first).
  - Strength fields only take `"HIGH" | "MEDIUM" | "LOW"`.
- Verified multi-window S/R behavior on:
  - Oscillating synthetic datasets (clear HIGH strength levels).
  - Monotone (trending) series for fallback correctness.

### Weekly Trend (13+ tests)

- Insufficient data (< 42 bars) → `_NEUTRAL_WEEKLY_TREND`.
- Purely uptrend fixture → `weekly_trend == "BULLISH"` with correct relationships.
- Purely downtrend fixture → `weekly_trend == "BEARISH"`.
- All expected keys present and types correct.
- `weekly_trend_strength` in `{"STRONG", "MODERATE", "WEAK"}`.
- Integration:
  - `analyze_ticker` always returns a `weekly_trend` object.
  - `compute_swing_setup_pullback` conditions include `weekly_trend_aligned`.
  - Hard gate: ENTRY with bearish weekly → capped to WATCH, with `weekly_trend_warning`.
  - Backward compatibility: passing `weekly_trend=None` vs bullish weekly yields same verdict.

### RSI Cooldown (8+ tests)

Using `unittest.mock.patch` to control `RSIIndicator.rsi()`:

- Label & `rsi_ok` tests:
  - `healthy_pullback` (≥ 15 pts).
  - `moderate_pullback` (8–14 pts).
  - `mild_pullback` (3–7 pts).
  - `no_pullback` (< 3 pts).
  - Floor: `RSI < 35` → `no_pullback`.
  - Ceiling: `RSI > 70` → `no_pullback`.
- Score contribution deltas:
  - Healthy vs mild → exactly +7 points.
  - Mild vs no pullback → exactly +6 points.

### Trigger Logic (6+ tests)

For the new 3‑bar trigger:

- **All three conditions met**:
  - `trigger_ok=True`, `trigger_points=10`, `trigger_label="strong"`.
- **Price + volume only**:
  - `trigger_ok=True`, `trigger_points=7`, `trigger_label="moderate"`, `trigger_bar_strength_ok=False`.
- **Price + bar strength only**:
  - `trigger_ok=True`, `trigger_points=7`, `trigger_label="moderate"`, `trigger_volume_ok=False`.
- **Price only**:
  - `trigger_ok=True`, `trigger_points=4`, `trigger_label="weak"`, both confirmations False.
- **No price trigger**:
  - `trigger_ok=False`, `trigger_points=0`, `trigger_label="not_fired"`.
- **Doji edge case (bar_range=0)**:
  - `trigger_bar_strength_ok=False`.
  - No division error.
- Score-delta test:
  - Forcing trigger on vs off changes `setup_score` by **at least `trigger_points`**, acknowledging that other components may shift slightly with close changes.

### Verdict & Structure

- Structural tests on `compute_swing_setup_pullback` ensure:
  - All expected keys exist in `conditions`, `levels`, and `risk`.
  - `setup_score` always in **[0, 100]** across multiple trend regimes.
  - For a crafted ENTRY scenario, `uptrend_confirmed` and `trigger_ok` are `True` and score is sufficiently high.
  - For a downtrend, `verdict == "NO_TRADE"` and `uptrend_confirmed=False`.

---

## 10. Multi-Timeframe Support — Deferred to Next Session

### Proposed Enhancement

- Extend the engine to analyse:
  - **4‑hour** charts for tactical entries within daily WATCH setups.
  - Optionally **1‑hour** charts for more granular timing.

This would allow:

- Daily timeframe to define **where** to trade (trend + pullback + support).
- 4h/1h timeframes to define **when** (intraday confirmation, refined risk).

### Reason for Deferral

- This session focused on:
  - Making the **daily** engine robust (trend, support, RSI, trigger).
  - Ensuring confidence in the daily verdicts before increasing complexity.
- Consensus: run the improved daily system in live/desktop usage for a few weeks first.

### Recommended Starting Point

- Start with **4‑hour** only:
  - Captures 80% of the benefit with lower noise than 1h.
  - Simpler to visualise and reason about alongside daily.
- Once stable, add optional **1‑hour** signals on top (likely as a refinement, not a new gate).

### yfinance Support

- **1h data** is available for up to **730 days**.
- **4h data** can be derived by **resampling 1h bars** using `pandas.DataFrame.resample('4H')`:
  - `open`: first.
  - `high`: max.
  - `low`: min.
  - `close`: last.
  - `volume`: sum.

---

## 11. Current Verdict Logic Reference

### Verdict Rules

| Verdict    | Requirements                                                                 |
|-----------|------------------------------------------------------------------------------|
| **ENTRY** | `uptrend_confirmed` AND `near_support` AND `reversal_found` AND `trigger_ok` AND `score ≥ 70` |
| **WATCH** | `uptrend_confirmed` AND (`near_support` OR `rsi_ok`) AND `score ≥ 55`        |
| **NO_TRADE** | Anything else                                                            |

**Weekly gate:**

- If `weekly_trend_aligned == False` and `verdict == "ENTRY"`, verdict is downgraded to `WATCH` and `weekly_trend_warning` is set.

### Scoring Breakdown

| Component                                       | Max Points |
|------------------------------------------------|-----------:|
| Uptrend confirmed (price vs SMA50/200)         | 30         |
| ADX strength (trend strength)                  | 10         |
| Pullback quality (RSI cooldown + near support) | 25         |
| Volume / OBV (declining volume, rising OBV)    | 10         |
| Reversal candle                                | 15         |
| Trigger (3‑bar breakout, tiered)               | 10         |
| **Total**                                      | **100**    |

---

## 12. Known Limitations & Next Session Backlog

### Limitations

- **Score thresholds (70 for ENTRY, 55 for WATCH)**:
  - Not yet tuned via systematic backtesting.
  - Currently based on expert judgment and unit tests.
- **R:R minimum threshold not enforced**:
  - `rr_to_resistance` is computed but:
    - No hard floor (e.g. `R:R >= 1.5x`) is currently enforced.
    - Setups with poor R:R (< 0.3x) are not flagged or downgraded automatically.
- **No sector/market context**:
  - A pullback during a broad market sell-off scores the same as one in a strong risk-on environment.
  - No integration with index/sector breadth metrics.
- **Support accuracy still tied to `argrelextrema`**:
  - Very recent swing lows (< `order` bars confirmed) may not yet be detected.
  - Some “fresh” supports may not appear in the S/R structure immediately.
- **Weekly trend uses only SMA10/40**:
  - Does not yet incorporate:
    - Weekly RSI.
    - Weekly candlestick patterns.
    - Macro/sector overlays.
- **Multi-timeframe (4h/1h)**:
  - Not implemented; see Section 10.
- **Backtesting replayer**:
  - Needed to:
    - Tune thresholds (70/55).
    - Validate scoring weights per component.
    - Explore outcome distributions (win rate vs score decile).

### Backlog / Next Steps

- Build a **backtesting replayer**:
  - Use stored daily/weekly price histories.
  - Step through time, compute swing setups daily.
  - Record outcomes and calibrate thresholds and weights.
- Add **R:R quality flags** and possibly a minimum R:R gate for ENTRY.
- Introduce **sector/index context** (e.g. compare to SPY/QQQ/XLF/XLE trends).
- Extend S/R detection with:
  - Optional volume‑by‑price overlays.
  - Recent bar low/high “provisional” levels.
- Add **4h timeframe support** for entry timing.

---

## Starting Point for Next Session

- **Daily swing engine** is now structurally robust: S/R, weekly trend, RSI cooldown, and trigger logic are all integrated and tested.
- **Verdict rules** are clearly defined and isolated; WATCH no longer depends on reversal/trigger, while ENTRY remains strict and weekly‑gated.
- **Outputs are frontend‑friendly**: strength labels, trigger tiers, RSI pullback labels, and candlestick names are all human-readable.
- **Tests cover core logic**: RSI cooldown, trigger tiers, S/R invariants, weekly trend gating, and swing setup structure are all under unit tests.
- **Next big investment** should be in a **backtesting replayer and 4h timeframe integration**, using the current scoring model as the baseline for tuning. 

