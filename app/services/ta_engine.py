import numpy as np
import pandas as pd
import talib
from scipy.signal import argrelextrema
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator


_NEUTRAL_WEEKLY_TREND: dict = {
    "weekly_trend": "NEUTRAL",
    "weekly_sma10": None,
    "weekly_sma40": None,
    "price_vs_weekly_sma10": "below",
    "price_vs_weekly_sma40": "below",
    "weekly_sma10_vs_sma40": "below",
    "weekly_trend_strength": "WEAK",
}

_NEUTRAL_4H: dict = {
    "four_h_reversal":      False,
    "four_h_trigger":       False,
    "four_h_rsi":           0.0,
    "four_h_rsi_ok":        False,
    "four_h_confirmed":     False,
    "four_h_available":     False,
    "four_h_reversal_name": None,
}


def _prepare_dataframe(price_list: list[dict]) -> pd.DataFrame:
    """Convert list[dict] from DB → DataFrame with DatetimeIndex."""
    df = pd.DataFrame(price_list)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df.astype({
        "open": float, "high": float, "low": float,
        "close": float, "volume": float,
    })
    return df


def compute_trend_signals(df: pd.DataFrame) -> dict:
    """SMA 20/50/200, EMA 9/21, golden/death cross, price vs MA positions."""
    close = df["close"]
    price = close.iloc[-1]

    sma_20 = SMAIndicator(close, window=20).sma_indicator()
    sma_50 = SMAIndicator(close, window=50).sma_indicator()
    sma_200 = SMAIndicator(close, window=200).sma_indicator()
    ema_9 = EMAIndicator(close, window=9).ema_indicator()
    ema_21 = EMAIndicator(close, window=21).ema_indicator()

    def _last_val(series):
        val = series.iloc[-1]
        return float(val) if pd.notna(val) else None

    sma_20_val = _last_val(sma_20)
    sma_50_val = _last_val(sma_50)
    sma_200_val = _last_val(sma_200)
    ema_9_val = _last_val(ema_9)
    ema_21_val = _last_val(ema_21)

    def _pct_distance(ma_val):
        if ma_val is None or ma_val == 0:
            return None
        return round((price - ma_val) / ma_val * 100, 2)

    # Golden cross: SMA50 crosses above SMA200
    # Death cross: SMA50 crosses below SMA200
    golden_cross = False
    death_cross = False
    if len(sma_50.dropna()) >= 2 and len(sma_200.dropna()) >= 2:
        prev_50 = sma_50.iloc[-2]
        prev_200 = sma_200.iloc[-2]
        curr_50 = sma_50.iloc[-1]
        curr_200 = sma_200.iloc[-1]
        if not any(pd.isna([prev_50, prev_200, curr_50, curr_200])):
            golden_cross = bool(prev_50 <= prev_200 and curr_50 > curr_200)
            death_cross = bool(prev_50 >= prev_200 and curr_50 < curr_200)

    # Overall signal
    signal = "NEUTRAL"
    if sma_200_val is not None:
        above_200 = price > sma_200_val
        if above_200 and not death_cross:
            signal = "BULLISH"
        elif not above_200 or death_cross:
            signal = "BEARISH"

    return {
        "sma_20": sma_20_val,
        "sma_50": sma_50_val,
        "sma_200": sma_200_val,
        "ema_9": ema_9_val,
        "ema_21": ema_21_val,
        "price_vs_sma20": "above" if sma_20_val and price > sma_20_val else "below",
        "price_vs_sma50": "above" if sma_50_val and price > sma_50_val else "below",
        "price_vs_sma200": "above" if sma_200_val and price > sma_200_val else "below",
        "distance_from_sma20_pct": _pct_distance(sma_20_val),
        "distance_from_sma50_pct": _pct_distance(sma_50_val),
        "distance_from_sma200_pct": _pct_distance(sma_200_val),
        "golden_cross": golden_cross,
        "death_cross": death_cross,
        "signal": signal,
    }


def compute_momentum_signals(df: pd.DataFrame) -> dict:
    """RSI(14), MACD(12,26,9) + crossover, Stochastic(14,3)."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # RSI
    rsi_indicator = RSIIndicator(close, window=14)
    rsi_series = rsi_indicator.rsi()
    rsi_val = float(rsi_series.iloc[-1]) if pd.notna(rsi_series.iloc[-1]) else None

    rsi_signal = "NEUTRAL"
    if rsi_val is not None:
        if rsi_val > 70:
            rsi_signal = "OVERBOUGHT"
        elif rsi_val > 60:
            rsi_signal = "MODERATE_BULLISH"
        elif rsi_val < 30:
            rsi_signal = "OVERSOLD"
        elif rsi_val < 40:
            rsi_signal = "MODERATE_BEARISH"

    # MACD
    macd_indicator = MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_indicator.macd()
    macd_signal_line = macd_indicator.macd_signal()
    macd_hist_line = macd_indicator.macd_diff()

    macd_val = float(macd_line.iloc[-1]) if pd.notna(macd_line.iloc[-1]) else None
    macd_signal_val = float(macd_signal_line.iloc[-1]) if pd.notna(macd_signal_line.iloc[-1]) else None
    macd_hist = float(macd_hist_line.iloc[-1]) if pd.notna(macd_hist_line.iloc[-1]) else None

    macd_crossover = "none"
    if len(macd_line.dropna()) >= 2 and len(macd_signal_line.dropna()) >= 2:
        prev_macd = macd_line.iloc[-2]
        prev_signal = macd_signal_line.iloc[-2]
        curr_macd = macd_line.iloc[-1]
        curr_signal = macd_signal_line.iloc[-1]
        if not any(pd.isna([prev_macd, prev_signal, curr_macd, curr_signal])):
            if prev_macd <= prev_signal and curr_macd > curr_signal:
                macd_crossover = "bullish_crossover"
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                macd_crossover = "bearish_crossover"

    # Stochastic oscillator (manual calculation since ta uses StochRSI)
    low_14 = low.rolling(window=14).min()
    high_14 = high.rolling(window=14).max()
    stoch_k_series = ((close - low_14) / (high_14 - low_14)) * 100
    stoch_d_series = stoch_k_series.rolling(window=3).mean()

    stoch_k = float(stoch_k_series.iloc[-1]) if pd.notna(stoch_k_series.iloc[-1]) else None
    stoch_d = float(stoch_d_series.iloc[-1]) if pd.notna(stoch_d_series.iloc[-1]) else None
    stoch_signal = "NEUTRAL"
    if stoch_k is not None:
        if stoch_k > 80:
            stoch_signal = "OVERBOUGHT"
        elif stoch_k < 20:
            stoch_signal = "OVERSOLD"

    # Overall momentum signal
    signal = "NEUTRAL"
    if rsi_val is not None:
        if rsi_val > 70:
            signal = "BEARISH"
        elif rsi_val < 30:
            signal = "BULLISH"
        elif macd_crossover == "bullish_crossover":
            signal = "BULLISH"
        elif macd_crossover == "bearish_crossover":
            signal = "BEARISH"

    return {
        "rsi": round(rsi_val, 2) if rsi_val is not None else None,
        "rsi_signal": rsi_signal,
        "macd": round(macd_val, 4) if macd_val is not None else None,
        "macd_signal": round(macd_signal_val, 4) if macd_signal_val is not None else None,
        "macd_histogram": round(macd_hist, 4) if macd_hist is not None else None,
        "macd_crossover": macd_crossover,
        "stochastic_k": round(stoch_k, 2) if stoch_k is not None else None,
        "stochastic_d": round(stoch_d, 2) if stoch_d is not None else None,
        "stochastic_signal": stoch_signal,
        "signal": signal,
    }


def compute_volatility_signals(df: pd.DataFrame) -> dict:
    """Bollinger Bands(20,2), BB squeeze, ATR(14)."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    price = close.iloc[-1]

    # Bollinger Bands
    bb = BollingerBands(close, window=20, window_dev=2)
    bb_upper_series = bb.bollinger_hband()
    bb_middle_series = bb.bollinger_mavg()
    bb_lower_series = bb.bollinger_lband()

    bb_upper = float(bb_upper_series.iloc[-1]) if pd.notna(bb_upper_series.iloc[-1]) else None
    bb_middle = float(bb_middle_series.iloc[-1]) if pd.notna(bb_middle_series.iloc[-1]) else None
    bb_lower = float(bb_lower_series.iloc[-1]) if pd.notna(bb_lower_series.iloc[-1]) else None

    bb_width = bb_position = None
    bb_squeeze = False
    if bb_upper is not None and bb_lower is not None and bb_middle:
        bb_width = round((bb_upper - bb_lower) / bb_middle * 100, 2)
        if (bb_upper - bb_lower) != 0:
            bb_position = round((price - bb_lower) / (bb_upper - bb_lower) * 100, 2)

        # Squeeze: BB width is in lowest 20% of its 120-day range
        width_series = (bb_upper_series - bb_lower_series) / bb_middle_series * 100
        width_clean = width_series.dropna()
        if len(width_clean) >= 120:
            recent_width = width_clean.iloc[-120:]
            threshold = recent_width.quantile(0.2)
            bb_squeeze = bool(width_clean.iloc[-1] <= threshold)

    # ATR
    atr_indicator = AverageTrueRange(high, low, close, window=14)
    atr_series = atr_indicator.average_true_range()
    atr_val = float(atr_series.iloc[-1]) if pd.notna(atr_series.iloc[-1]) else None
    atr_pct = round(atr_val / price * 100, 2) if atr_val and price else None

    # Overall signal
    signal = "NORMAL"
    if atr_pct is not None:
        if atr_pct > 3:
            signal = "HIGH_VOLATILITY"
        elif atr_pct < 1:
            signal = "LOW_VOLATILITY"

    return {
        "bb_upper": round(bb_upper, 2) if bb_upper is not None else None,
        "bb_middle": round(bb_middle, 2) if bb_middle is not None else None,
        "bb_lower": round(bb_lower, 2) if bb_lower is not None else None,
        "bb_width": bb_width,
        "bb_position": bb_position,
        "bb_squeeze": bb_squeeze,
        "atr": round(atr_val, 2) if atr_val is not None else None,
        "atr_vs_price_pct": atr_pct,
        "signal": signal,
    }


def compute_volume_signals(df: pd.DataFrame) -> dict:
    """Volume vs 20d avg, OBV + trend."""
    volume = df["volume"]
    close = df["close"]
    current_vol = float(volume.iloc[-1])

    avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
    volume_ratio = round(current_vol / avg_vol_20, 2) if avg_vol_20 else None

    volume_signal = "NORMAL"
    if volume_ratio is not None:
        if volume_ratio > 1.5:
            volume_signal = "HIGH"
        elif volume_ratio < 0.7:
            volume_signal = "LOW"

    # OBV
    obv_indicator = OnBalanceVolumeIndicator(close, volume)
    obv_series = obv_indicator.on_balance_volume()
    obv_val = float(obv_series.iloc[-1]) if pd.notna(obv_series.iloc[-1]) else None

    # OBV trend: compare current OBV to 20-day SMA of OBV
    obv_trend = "NEUTRAL"
    if obv_val is not None and len(obv_series.dropna()) >= 20:
        obv_sma = obv_series.rolling(20).mean().iloc[-1]
        if pd.notna(obv_sma):
            obv_trend = "RISING" if obv_val > obv_sma else "FALLING"

    return {
        "current_volume": int(current_vol),
        "avg_volume_20d": int(avg_vol_20),
        "volume_ratio": volume_ratio,
        "volume_signal": volume_signal,
        "obv": int(obv_val) if obv_val is not None else None,
        "obv_trend": obv_trend,
    }


def _get_provisional_levels(
    df: pd.DataFrame,
    current_price: float,
    n_bars: int = 7,
    max_distance_pct: float = 8.0,
) -> dict:
    """
    Derives provisional support/resistance from the recent n_bars window.
    These levels are structurally unconfirmed (argrelextrema has not yet
    validated them) but are meaningful for fresh pullback detection.

    Returns a dict with:
        provisional_support:    float | None
        provisional_resistance: float | None
        provisional_support_distance_pct:    float | None
        provisional_resistance_distance_pct: float | None
    """
    if len(df) <= 1:
        return {
            "provisional_support": None,
            "provisional_resistance": None,
            "provisional_support_distance_pct": None,
            "provisional_resistance_distance_pct": None,
        }

    recent = df.iloc[-(n_bars + 1):-1]  # exclude today's bar
    if recent.empty:
        return {
            "provisional_support": None,
            "provisional_resistance": None,
            "provisional_support_distance_pct": None,
            "provisional_resistance_distance_pct": None,
        }

    raw_low = float(recent["low"].min())
    raw_high = float(recent["high"].max())

    prov_support = round(raw_low, 2) if raw_low < current_price else None
    prov_resistance = round(raw_high, 2) if raw_high > current_price else None

    support_dist = (
        round((current_price - prov_support) / current_price * 100, 2)
        if prov_support is not None else None
    )
    resistance_dist = (
        round((prov_resistance - current_price) / current_price * 100, 2)
        if prov_resistance is not None else None
    )

    # Discard if too far from price — likely not a fresh level
    if support_dist is not None and support_dist > max_distance_pct:
        prov_support = None
        support_dist = None
    if resistance_dist is not None and resistance_dist > max_distance_pct:
        prov_resistance = None
        resistance_dist = None

    return {
        "provisional_support": prov_support,
        "provisional_resistance": prov_resistance,
        "provisional_support_distance_pct": support_dist,
        "provisional_resistance_distance_pct": resistance_dist,
    }


def compute_support_resistance(df: pd.DataFrame, swing_lookback: int = 90) -> dict:
    """Multi-window clustered S/R with touch-count significance scoring.

    Three lookback windows are run simultaneously and combined before clustering,
    so that recent structure, 1-year majors, and 2-year historical levels all
    contribute to the final level set.

    Args:
        swing_lookback: Retained for backward compatibility; no longer used
            internally. Previously controlled a single lookback window; the
            implementation now always uses three fixed windows (90/252/504 days).
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    price = float(close.iloc[-1])
    high_vals = high.values
    low_vals = low.values

    # ── 52-week metrics (unchanged from v1) ──────────────────────────────────
    lookback_252 = min(len(df), 252)
    recent_252 = df.iloc[-lookback_252:]
    high_52w = float(recent_252["high"].max())
    low_52w = float(recent_252["low"].min())
    dist_from_52w_high = round((price - high_52w) / high_52w * 100, 2)
    dist_from_52w_low = round((price - low_52w) / low_52w * 100, 2)

    # ── Step 1: Multi-window swing detection ─────────────────────────────────
    # Each (window_days, order) pair targets a different market structure scale.
    # Smaller order → more sensitive to recent swings.
    # Larger order → only captures truly prominent turning points.
    _WINDOWS: list[tuple[int, int]] = [
        (90,  3),   # recent structure — last ~4 months, sensitive detection
        (252, 5),   # 1-year major levels — filters out noise
        (504, 8),   # 2-year significant levels — only major turning points
    ]

    raw_highs: list[float] = []
    raw_lows: list[float] = []

    for window_days, order in _WINDOWS:
        n = min(len(df), window_days)
        window_df = df.iloc[-n:]
        hi_idx = argrelextrema(window_df["high"].values, np.greater_equal, order=order)[0]
        lo_idx = argrelextrema(window_df["low"].values, np.less_equal, order=order)[0]
        raw_highs.extend(float(window_df["high"].iloc[i]) for i in hi_idx)
        raw_lows.extend(float(window_df["low"].iloc[i]) for i in lo_idx)

    # ── Step 2: Cluster nearby levels (within 1%) ────────────────────────────
    def _cluster(levels: list[float], tol_pct: float = 1.0) -> list[float]:
        """Merge levels within tol_pct of the cluster's anchor (first member)."""
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

    clustered_highs = _cluster(raw_highs)
    clustered_lows = _cluster(raw_lows)

    # ── Step 3: Score each level by touch count over full price history ───────
    def _score(level: float) -> tuple[int, str]:
        """Count bars where the candle range overlaps the ±0.5% band around level."""
        band_lo = level * 0.995
        band_hi = level * 1.005
        touches = int(np.sum((high_vals >= band_lo) & (low_vals <= band_hi)))
        if touches >= 3:
            return 3, "HIGH"
        if touches >= 2:
            return 2, "MEDIUM"
        return 1, "LOW"

    # Tuples of (price, weight, strength_label)
    scored_highs: list[tuple[float, int, str]] = [(lvl, *_score(lvl)) for lvl in clustered_highs]
    scored_lows: list[tuple[float, int, str]] = [(lvl, *_score(lvl)) for lvl in clustered_lows]

    # ── Step 4: Select nearest support / resistance with weight preference ────
    def _pick_nearest(
        candidates: list[tuple[float, int, str]],
        above: bool,
    ) -> tuple[float, str] | tuple[None, None]:
        """Return (price, strength) of the best level.

        'Best' = nearest to current price, but if two candidates are within 1%
        of each other the higher-weight one wins (tie-break: closer to price).
        """
        if not candidates:
            return None, None
        # Sort so [0] is always the raw nearest level
        sorted_cands = sorted(candidates, key=lambda x: x[0] if above else -x[0])
        nearest = sorted_cands[0]
        # Gather all candidates within 1% of the raw nearest
        close_group = [
            c for c in sorted_cands
            if abs(c[0] - nearest[0]) / nearest[0] * 100 <= 1.0
        ]
        # Highest weight wins; tie-break by absolute distance to current price
        best = max(close_group, key=lambda x: (x[1], -abs(x[0] - price)))
        return round(best[0], 2), best[2]

    resistance_candidates = [(p, w, s) for p, w, s in scored_highs if p > price]
    support_candidates = [(p, w, s) for p, w, s in scored_lows if p < price]

    nearest_resistance_val, resistance_strength = _pick_nearest(resistance_candidates, above=True)
    nearest_support_val, support_strength = _pick_nearest(support_candidates, above=False)

    has_confirmed_resistance = nearest_resistance_val is not None
    has_confirmed_support = nearest_support_val is not None

    # Fall back to 52w extremes when no swing points found
    if nearest_resistance_val is None:
        nearest_resistance_val, resistance_strength = high_52w, "LOW"
    if nearest_support_val is None:
        nearest_support_val, support_strength = low_52w, "LOW"

    # ── Step 5: Top-5 annotated level lists (nearest first) ──────────────────
    # swing_highs: resistance levels strictly above current price, nearest first.
    top_highs = sorted(
        [(p, w, s) for p, w, s in scored_highs if p > price],
        key=lambda x: x[0],
    )[:5]

    # swing_lows: support levels strictly below current price, nearest first.
    top_lows = sorted(
        [(p, w, s) for p, w, s in scored_lows if p < price],
        key=lambda x: -x[0],
    )[:5]

    # If no swing-based resistance exists above price, fall back to 52w high.
    if not top_highs:
        top_highs = [(high_52w, 1, "LOW")]

    # If no swing-based support exists below price, fall back to 52w low.
    if not top_lows:
        top_lows = [(low_52w, 1, "LOW")]

    swing_highs_out = [{"price": round(p, 2), "strength": s} for p, _, s in top_highs]
    swing_lows_out = [{"price": round(p, 2), "strength": s} for p, _, s in top_lows]

    # ── Step 6: Provisional recency-based levels (fallback) ─────────────────────
    provisional = _get_provisional_levels(df, price)

    support_is_provisional = False
    resistance_is_provisional = False

    prov_support = provisional["provisional_support"]
    prov_support_dist = provisional["provisional_support_distance_pct"]
    prov_resistance = provisional["provisional_resistance"]
    prov_resistance_dist = provisional["provisional_resistance_distance_pct"]

    # Fallback: use provisional support if confirmed support is more than 3% away
    # AND provisional is closer (or when no confirmed support exists).
    if prov_support is not None and prov_support_dist is not None:
        confirmed_support_dist = (
            abs(price - nearest_support_val) / price * 100 if has_confirmed_support else None
        )
        use_provisional_support = False
        if confirmed_support_dist is None:
            use_provisional_support = True
        elif confirmed_support_dist > 3.0 and prov_support_dist < confirmed_support_dist:
            use_provisional_support = True

        if use_provisional_support:
            nearest_support_val = prov_support
            support_strength = "LOW"
            support_is_provisional = True

    # Same logic for resistance
    if prov_resistance is not None and prov_resistance_dist is not None:
        confirmed_resistance_dist = (
            abs(nearest_resistance_val - price) / price * 100 if has_confirmed_resistance else None
        )
        use_provisional_resistance = False
        if confirmed_resistance_dist is None:
            use_provisional_resistance = True
        elif confirmed_resistance_dist > 3.0 and prov_resistance_dist < confirmed_resistance_dist:
            use_provisional_resistance = True

        if use_provisional_resistance:
            nearest_resistance_val = prov_resistance
            resistance_strength = "LOW"
            resistance_is_provisional = True

    dist_to_resistance = round((nearest_resistance_val - price) / price * 100, 2)
    dist_to_support = round((price - nearest_support_val) / price * 100, 2)

    return {
        "high_52w": high_52w,
        "low_52w": low_52w,
        "distance_from_52w_high_pct": dist_from_52w_high,
        "distance_from_52w_low_pct": dist_from_52w_low,
        "swing_highs": swing_highs_out,
        "swing_lows": swing_lows_out,
        "nearest_resistance": nearest_resistance_val,
        "nearest_support": nearest_support_val,
        "distance_to_resistance_pct": dist_to_resistance,
        "distance_to_support_pct": dist_to_support,
        "support_strength": support_strength,
        "resistance_strength": resistance_strength,
        "support_is_provisional": support_is_provisional,
        "resistance_is_provisional": resistance_is_provisional,
        "provisional_support": provisional["provisional_support"],
        "provisional_resistance": provisional["provisional_resistance"],
    }


def compute_candlestick_patterns(df: pd.DataFrame, support_resistance: dict) -> list[dict]:
    """Detect candlestick patterns via TA-Lib and assess significance based on S/R proximity."""
    price = df["close"].iloc[-1]
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    nearest_support = support_resistance.get("nearest_support", 0)
    nearest_resistance = support_resistance.get("nearest_resistance", 0)

    at_support = abs(price - nearest_support) / price * 100 < 2 if nearest_support else False
    at_resistance = abs(price - nearest_resistance) / price * 100 < 2 if nearest_resistance else False
    significance = "HIGH" if (at_support or at_resistance) else "LOW"

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

    # Get all TA-Lib candlestick pattern functions (CDL*)
    candle_funcs = talib.get_function_groups()["Pattern Recognition"]

    patterns = []
    for func_name in candle_funcs:
        func = getattr(talib, func_name)
        result = func(o, h, l, c)
        last_val = int(result[-1])
        if last_val != 0:
            raw_name = func_name.replace("CDL", "").lower()
            display_name = PATTERN_NAMES.get(raw_name, raw_name.replace("_", " ").title())
            pattern_type = "bullish" if last_val > 0 else "bearish"
            patterns.append({
                "pattern": display_name,
                "pattern_type": pattern_type,
                "at_support": at_support,
                "at_resistance": at_resistance,
                "significance": significance,
            })

    return patterns


_BULLISH_REVERSAL_ALLOWLIST: frozenset[str] = frozenset({
    "CDLENGULFING",
    "CDLHAMMER",
    "CDLINVERTEDHAMMER",
    "CDLPIERCING",
    "CDLMORNINGSTAR",
    "CDLMORNINGDOJISTAR",
    "CDLHARAMI",
    "CDLHARAMICROSS",
})


def _find_reversal_candles(df: pd.DataFrame, scan_bars: int = 5) -> list[dict]:
    """Scan the last scan_bars for bullish reversal patterns from the allowlist.

    Returns one entry per matched CDL function (most recent bullish bar in window),
    sorted by bars_ago ascending (most-recent first), then strength descending.
    """
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    found: list[dict] = []
    for func_name in _BULLISH_REVERSAL_ALLOWLIST:
        func = getattr(talib, func_name)
        result = func(o, h, l, c)
        window = result[-scan_bars:]
        # Iterate newest → oldest; take only the most recent bullish occurrence
        for i in range(len(window) - 1, -1, -1):
            val = int(window[i])
            if val > 0:
                bars_ago = (len(window) - 1) - i
                found.append({
                    "pattern": func_name.replace("CDL", "").lower(),
                    "bars_ago": bars_ago,
                    "raw_value": val,
                    "strength": "strong" if abs(val) >= 200 else "normal",
                })
                break  # only the most recent hit per pattern

    # Sort: most recent first, then strongest first within same recency
    found.sort(key=lambda x: (x["bars_ago"], 0 if x["strength"] == "strong" else 1))
    return found


def compute_weekly_trend(weekly_df: pd.DataFrame) -> dict:
    """Compute weekly trend using SMA10 and SMA40 on a weekly OHLCV DataFrame.

    Requires at least 42 bars (SMA40 + 2-bar buffer) to be valid; returns
    _NEUTRAL_WEEKLY_TREND if data is missing or insufficient.
    """
    if weekly_df is None or len(weekly_df) < 42:
        return _NEUTRAL_WEEKLY_TREND.copy()

    close = weekly_df["close"]
    price = float(close.iloc[-1])

    sma10_series = SMAIndicator(close, window=10).sma_indicator()
    sma40_series = SMAIndicator(close, window=40).sma_indicator()

    sma10_val = float(sma10_series.iloc[-1]) if pd.notna(sma10_series.iloc[-1]) else None
    sma40_val = float(sma40_series.iloc[-1]) if pd.notna(sma40_series.iloc[-1]) else None

    if sma10_val is None or sma40_val is None:
        return _NEUTRAL_WEEKLY_TREND.copy()

    above_sma10      = price > sma10_val
    above_sma40      = price > sma40_val
    sma10_above_sma40 = sma10_val > sma40_val

    if above_sma10 and above_sma40 and sma10_above_sma40:
        weekly_trend = "BULLISH"
    elif not above_sma10 and not above_sma40 and not sma10_above_sma40:
        weekly_trend = "BEARISH"
    else:
        weekly_trend = "NEUTRAL"

    dist_from_sma40_pct = abs(price - sma40_val) / sma40_val * 100
    if weekly_trend in ("BULLISH", "BEARISH") and dist_from_sma40_pct > 2.0:
        weekly_trend_strength = "STRONG"
    elif weekly_trend in ("BULLISH", "BEARISH"):
        weekly_trend_strength = "MODERATE"
    else:
        weekly_trend_strength = "WEAK"

    return {
        "weekly_trend":            weekly_trend,
        "weekly_sma10":            round(sma10_val, 2),
        "weekly_sma40":            round(sma40_val, 2),
        "price_vs_weekly_sma10":   "above" if above_sma10 else "below",
        "price_vs_weekly_sma40":   "above" if above_sma40 else "below",
        "weekly_sma10_vs_sma40":   "above" if sma10_above_sma40 else "below",
        "weekly_trend_strength":   weekly_trend_strength,
    }


def _classify_rr_ratio(rr_ratio: float | None, min_rr_ratio: float = 1.5) -> tuple[str, bool]:
    """Classify R:R ratio into label + gate flag.

    Returns (rr_label, rr_gate_pass). Uses min_rr_ratio for 'good' threshold
    when provided (e.g. from backtest config).
    """
    if rr_ratio is None:
        return "unavailable", True
    if rr_ratio >= min_rr_ratio:
        return "good", True
    if rr_ratio >= 1.0:
        return "marginal", True
    if rr_ratio >= 0.5:
        return "poor", False
    return "bad", False


def _apply_rr_gate(
    verdict: str,
    rr_ratio: float | None,
    rr_label: str,
    rr_gate_pass: bool,
) -> tuple[str, str | None]:
    """Apply the R:R hard gate on top of the primary verdict.

    Returns (possibly_downgraded_verdict, rr_warning).
    """
    rr_warning: str | None = None

    if verdict == "ENTRY" and rr_label in ("marginal",):
        rr_warning = "R:R is marginal — consider waiting for a better entry point"

    if verdict == "ENTRY" and not rr_gate_pass:
        verdict = "WATCH"
        rr_warning = (
            f"R:R of {rr_ratio}:1 is too poor for entry — "
            "resistance is too close or stop is too wide"
        )

    if rr_label == "bad":
        verdict = "NO_TRADE"
        rr_warning = (
            f"R:R of {rr_ratio}:1 makes this setup unfavourable regardless of other conditions"
        )

    return verdict, rr_warning


def _support_strength_rank(s: str) -> int:
    """LOW=0, MEDIUM=1, HIGH=2 for min_support_strength filtering."""
    return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get((s or "").upper(), -1)


def _support_strength_meets_minimum(strength: str | None, minimum: str | None) -> bool:
    """Return True if *strength* meets or exceeds *minimum*, or if no minimum is configured."""
    if not minimum:
        return True
    return _support_strength_rank(strength) >= _support_strength_rank(minimum)


def compute_swing_setup_pullback(
    df: pd.DataFrame,
    trend: dict,
    momentum: dict,
    volatility: dict,
    volume: dict,
    support_resistance: dict,
    weekly_trend: dict | None = None,
    *,
    entry_score_threshold: int = 70,
    watch_score_threshold: int = 55,
    min_rr_ratio: float = 1.5,
    require_weekly_aligned: bool = True,
    min_support_strength: str | None = None,
) -> dict:
    """Detect a bullish 'Pullback in Uptrend' daily swing setup.

    Scores 0-100 and returns verdict: ENTRY / WATCH / NO_TRADE.
    All inputs are pre-computed signal dicts from analyze_ticker; no re-fetching.
    """
    price = float(df["close"].iloc[-1])

    # ── Weekly trend alignment (hard gate — no score impact) ─────────────────
    # If weekly_trend is None (no data / direct call from tests) treat as aligned
    # so existing tests and callers without weekly data are not penalised.
    # When require_weekly_aligned is False, gate is disabled (treat as aligned).
    _wt = weekly_trend or {}
    weekly_trend_aligned: bool = (
        not require_weekly_aligned
        or weekly_trend is None
        or _wt.get("weekly_trend") == "BULLISH"
    )

    # ── A) Uptrend confirmation ───────────────────────────────────────────────
    sma_50_val = trend.get("sma_50") or 0.0
    sma_200_val = trend.get("sma_200") or 0.0
    uptrend_confirmed: bool = bool(
        trend.get("price_vs_sma200") == "above"
        and trend.get("price_vs_sma50") == "above"
        and sma_50_val > sma_200_val
    )

    # ADX — not computed elsewhere; scoped locally to swing setup
    h_arr = df["high"].values
    l_arr = df["low"].values
    c_arr = df["close"].values
    adx_arr = talib.ADX(h_arr, l_arr, c_arr, timeperiod=14)
    adx_clean = adx_arr[~np.isnan(adx_arr)]
    adx_val: float = round(float(adx_clean[-1]), 2) if len(adx_clean) > 0 else 0.0
    adx_strong: bool = adx_val >= 20

    # ── B) Pullback quality ───────────────────────────────────────────────────
    rsi: float = float(momentum.get("rsi") or 0.0)

    # RSI cooldown-from-peak: measures how far RSI has pulled back from its
    # recent high rather than checking a fixed band.
    _rsi_series = RSIIndicator(df["close"], window=14).rsi()
    _rsi_peak_raw = _rsi_series.iloc[-20:].max()
    rsi_peak: float = float(_rsi_peak_raw) if pd.notna(_rsi_peak_raw) else rsi
    rsi_cooldown: float = round(rsi_peak - rsi, 1)

    if rsi < 35 or rsi > 70:
        # Floor: momentum collapse / Ceiling: still overbought
        rsi_ok, rsi_label = False, "no_pullback"
    elif rsi_cooldown >= 15:
        rsi_ok, rsi_label = True, "healthy_pullback"
    elif rsi_cooldown >= 8:
        rsi_ok, rsi_label = True, "moderate_pullback"
    elif rsi_cooldown >= 3:
        rsi_ok, rsi_label = True, "mild_pullback"
    else:
        rsi_ok, rsi_label = False, "no_pullback"

    atr: float = float(volatility.get("atr") or 0.0)
    nearest_support: float = float(support_resistance.get("nearest_support") or 0.0)
    nearest_resistance: float = float(support_resistance.get("nearest_resistance") or 0.0)
    dist_to_support_pct: float = float(support_resistance.get("distance_to_support_pct") or 999.0)
    dist_to_resistance_pct: float = float(support_resistance.get("distance_to_resistance_pct") or 999.0)

    support_is_provisional: bool = bool(support_resistance.get("support_is_provisional") or False)
    resistance_is_provisional: bool = bool(support_resistance.get("resistance_is_provisional") or False)

    dist_to_support_abs: float = abs(price - nearest_support) if nearest_support > 0 else 999.0
    near_support_atr: bool = bool(atr > 0 and nearest_support > 0 and dist_to_support_abs <= 0.75 * atr)
    near_support_pct: bool = bool(nearest_support > 0 and dist_to_support_pct < 3.0)
    _near_support_raw: bool = near_support_atr or near_support_pct
    # Apply min_support_strength filter: skip near_support if strength below minimum
    support_strength_val: str = str(support_resistance.get("support_strength") or "LOW").upper()
    if min_support_strength and _support_strength_rank(support_strength_val) < _support_strength_rank(min_support_strength.upper()):
        near_support = False
    else:
        near_support = _near_support_raw

    dist_to_resistance_abs: float = abs(price - nearest_resistance) if nearest_resistance > 0 else 999.0
    near_resistance_atr: bool = bool(atr > 0 and nearest_resistance > 0 and dist_to_resistance_abs <= 0.75 * atr)
    near_resistance_pct: bool = bool(nearest_resistance > 0 and dist_to_resistance_pct < 3.0)
    near_resistance: bool = near_resistance_atr or near_resistance_pct

    volume_ratio: float = float(volume.get("volume_ratio") or 0.0)
    volume_declining: bool = volume_ratio < 1.0
    obv_trend: str = str(volume.get("obv_trend") or "NEUTRAL")

    # ── C) Candlestick confirmation ───────────────────────────────────────────
    reversal_candles = _find_reversal_candles(df, scan_bars=5)
    reversal_found: bool = bool(reversal_candles)

    # ── D) Trigger: 3-bar breakout with volume + bar-strength confirmation ──
    three_bar_high = float(df["high"].iloc[-4:-1].max())
    trigger_price: float = three_bar_high

    price_trigger: bool = bool(price > three_bar_high)

    current_volume: float = float(volume.get("current_volume") or 0.0)
    avg_volume_20d: float = float(volume.get("avg_volume_20d") or 0.0)
    trigger_volume_ok: bool = bool(
        avg_volume_20d > 0.0 and current_volume >= avg_volume_20d
    )

    bar_high = float(df["high"].iloc[-1])
    bar_low = float(df["low"].iloc[-1])
    bar_range = bar_high - bar_low
    trigger_bar_strength_ok: bool
    if bar_range > 0:
        trigger_bar_strength_ok = bool(
            (price - bar_low) / bar_range > 0.5
        )
    else:
        trigger_bar_strength_ok = False

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

    # ── E) Risk levels ────────────────────────────────────────────────────────
    if nearest_support > 0:
        entry_zone_low = round(nearest_support - 0.5 * atr, 2)
        entry_zone_high = round(nearest_support + 0.5 * atr, 2)
        stop_loss = round(nearest_support - 1.0 * atr, 2)
    else:
        entry_zone_low = round(price - 0.5 * atr, 2)
        entry_zone_high = round(price + 0.5 * atr, 2)
        stop_loss = round(price - 1.5 * atr, 2)

    if nearest_resistance > 0:
        target = round(nearest_resistance, 2)
    else:
        target = round(price + 2.0 * (price - stop_loss), 2)

    rr_to_resistance: float | None = None
    if nearest_resistance > 0 and price > stop_loss:
        rr_to_resistance = round((nearest_resistance - price) / (price - stop_loss), 2)

    # R:R ratio w.r.t nearest support / resistance (independent of stop-loss logic)
    if nearest_support and nearest_resistance and price > nearest_support:
        rr_ratio: float | None = round(
            (nearest_resistance - price) / (price - nearest_support),
            2,
        )
    else:
        rr_ratio = None

    rr_label, rr_gate_pass = _classify_rr_ratio(rr_ratio, min_rr_ratio)

    # ── F) SR alignment ───────────────────────────────────────────────────────
    if near_support:
        sr_alignment = "aligned"
    elif near_resistance:
        sr_alignment = "misaligned"
    else:
        sr_alignment = "neutral"

    # ── Scoring (0–100) ───────────────────────────────────────────────────────
    score = 0

    # Uptrend confirmation: 30 pts
    if uptrend_confirmed:
        score += 30

    # ADX: 10 pts, partial credit for 15–25
    if adx_val >= 25:
        score += 10
    elif adx_val >= 20:
        score += 7
    elif adx_val >= 15:
        score += 4

    # Pullback quality (RSI + near_support): 25 pts
    # RSI: 13 pts (healthy/moderate), 6 pts (mild), 0 pts (none)
    # near_support: 12 pts; combined max = 25
    rsi_pts = 13 if (rsi_ok and rsi_label != "mild_pullback") else (6 if rsi_label == "mild_pullback" else 0)
    score += rsi_pts + (12 if near_support else 0)

    # Volume / OBV: 10 pts
    if obv_trend == "RISING":
        score += 6
    if volume_declining:
        score += 4
    elif volume_ratio > 1.3:
        score -= 3  # elevated volume on pullback is a warning sign

    # Candlestick reversal: 15 pts
    if reversal_candles:
        min_bars_ago = min(rc["bars_ago"] for rc in reversal_candles)
        score += 15 if min_bars_ago <= 2 else 8

    # Trigger: up to 10 pts (3-bar breakout + confirmations)
    score += trigger_points

    score = max(0, min(100, score))

    # ── Verdict ───────────────────────────────────────────────────────────────
    in_entry_zone = entry_zone_low <= price <= entry_zone_high

    if (
        uptrend_confirmed
        and near_support
        and reversal_found
        and trigger_ok
        and score >= entry_score_threshold
    ):
        verdict = "ENTRY"
    elif (
        uptrend_confirmed
        and (near_support or rsi_ok)
        and score >= watch_score_threshold
    ):
        verdict = "WATCH"
    else:
        verdict = "NO_TRADE"

    # Weekly trend is a hard gate: cap ENTRY at WATCH when not aligned
    weekly_trend_warning: str | None = None
    if not weekly_trend_aligned and verdict == "ENTRY":
        verdict = "WATCH"
        weekly_trend_warning = "Daily setup forming against weekly trend — reduced conviction"

    # R:R gate applies after weekly trend gate
    verdict, rr_warning = _apply_rr_gate(verdict, rr_ratio, rr_label, rr_gate_pass)

    # ── Reasons ───────────────────────────────────────────────────────────────
    reasons: list[str] = [
        (
            f"uptrend_confirmed={uptrend_confirmed} "
            f"(price_vs_sma50={trend.get('price_vs_sma50')}, "
            f"price_vs_sma200={trend.get('price_vs_sma200')})"
        ),
        f"ADX={adx_val:.1f} adx_strong={adx_strong}",
        f"RSI={rsi:.1f} cooldown={rsi_cooldown:.1f}pts label={rsi_label} pullback_rsi_ok={rsi_ok}",
        (
            f"near_support={near_support} "
            f"(dist_pct={dist_to_support_pct:.1f}%, "
            f"dist_atr={dist_to_support_abs / atr:.2f}x)"
        ) if atr > 0 else (
            f"near_support={near_support} (dist_pct={dist_to_support_pct:.1f}%)"
        ),
        (
            f"volume_ratio={volume_ratio:.2f} "
            f"volume_declining={volume_declining} "
            f"obv_trend={obv_trend}"
        ),
    ]
    if reversal_candles:
        best = reversal_candles[0]
        reasons.append(
            f"reversal_candle={best['pattern']} "
            f"bars_ago={best['bars_ago']} strength={best['strength']}"
        )
    else:
        reasons.append("reversal_candle=none in last 5 bars")
    reasons.append(
        "trigger: "
        f"ok={trigger_ok} price_trigger={price_trigger} "
        f"volume_ok={trigger_volume_ok} bar_strength_ok={trigger_bar_strength_ok} "
        f"(close={price:.2f} vs trigger_price={trigger_price:.2f}, "
        f"points={trigger_points} label={trigger_label})"
    )

    return {
        "setup_type": "pullback_in_uptrend",
        "verdict": verdict,
        "setup_score": score,
        "weekly_trend_warning": weekly_trend_warning,
        "conditions": {
            "uptrend_confirmed": uptrend_confirmed,
            "weekly_trend_aligned": weekly_trend_aligned,
            "adx": adx_val,
            "adx_strong": adx_strong,
            "rsi": round(rsi, 2),
            "rsi_cooldown": rsi_cooldown,
            "rsi_pullback_label": rsi_label,
            "pullback_rsi_ok": rsi_ok,
            "near_support": near_support,
            "near_resistance": near_resistance,
            "volume_ratio": volume_ratio,
            "volume_declining": volume_declining,
            "obv_trend": obv_trend,
            "rr_ratio": rr_ratio,
            "rr_label": rr_label,
            "rr_gate_pass": rr_gate_pass,
            "rr_warning": rr_warning,
            "reversal_candle": {
                "found": reversal_found,
                "patterns": reversal_candles,
            },
            "trigger_ok": trigger_ok,
            "trigger_price": trigger_price,
            "trigger_volume_ok": trigger_volume_ok,
            "trigger_bar_strength_ok": trigger_bar_strength_ok,
            "trigger_points": trigger_points,
            "trigger_label": trigger_label,
        },
        "levels": {
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "sr_alignment": sr_alignment,
            "support_is_provisional": support_is_provisional,
            "resistance_is_provisional": resistance_is_provisional,
        },
        "risk": {
            "atr14": round(atr, 2),
            "entry_zone": {"low": entry_zone_low, "high": entry_zone_high},
            "stop_loss": stop_loss,
            "target": target,
            "rr_ratio": rr_ratio,
            "rr_to_resistance": rr_to_resistance,
        },
        "reasons": reasons,
    }


def _resample_to_4h(hourly_df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1H bars to 4H bars.

    Bars are aggregated on 4-hour UTC boundaries (00:00, 04:00, 08:00 …).
    Incomplete or all-NaN buckets are dropped via dropna().
    """
    if hourly_df is None or hourly_df.empty:
        return pd.DataFrame()

    df_4h = hourly_df.resample("4h").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna()

    return df_4h


def compute_4h_confirmation(hourly_df: pd.DataFrame) -> dict:
    """Resample 1H → 4H and check three confirmation conditions.

    Conditions:
      1. Bullish reversal candle on the most recent completed 4H bar (bars_ago <= 1)
      2. 4H trigger: close of most recent bar > highest high of the 3 bars before it
      3. 4H RSI(14) > 40 on the most recent bar

    Returns a dict with keys matching _NEUTRAL_4H.
    Never raises — returns _NEUTRAL_4H on any exception.
    """
    if hourly_df is None or hourly_df.empty:
        return _NEUTRAL_4H.copy()

    try:
        df_4h = _resample_to_4h(hourly_df)

        # Need at least 20 bars for RSI + 4 bars for trigger lookback
        if len(df_4h) < 20:
            return _NEUTRAL_4H.copy()

        # Exclude the currently forming (incomplete) bar — last bar may only
        # have 1-2 hours of data, making its OHLC misleading.
        df = df_4h.iloc[:-1].copy()

        if len(df) < 15:
            return _NEUTRAL_4H.copy()

        # ── Condition 1: bullish reversal candle ─────────────────────────────
        # Scan the last 3 completed 4H bars (≈12-16 market hours).
        # bars_ago <= 2 covers all three bars of the wider scan window.
        reversal_hits = _find_reversal_candles(df, scan_bars=3)
        bullish_hits = [h for h in reversal_hits if h.get("bars_ago", 99) <= 2]
        four_h_reversal = len(bullish_hits) > 0
        four_h_reversal_name = bullish_hits[0]["pattern"] if bullish_hits else None

        # ── Condition 2: 4H trigger (informational only) ──────────────────────
        # Close of most recent completed bar > highest high of the 3 bars before it.
        # Not required for four_h_confirmed — the trigger is a breakout signal that
        # is structurally anti-correlated with the daily WATCH state (which is a
        # pullback phase).  Retained here so callers can still read the field.
        if len(df) < 4:
            four_h_trigger = False
        else:
            recent_close   = float(df["close"].iloc[-1])
            three_bar_high = float(df["high"].iloc[-4:-1].max())
            four_h_trigger = recent_close > three_bar_high

        # ── Condition 3: 4H RSI > 40 ─────────────────────────────────────────
        rsi_series  = RSIIndicator(df["close"], window=14).rsi()
        four_h_rsi  = round(float(rsi_series.iloc[-1]), 1) if pd.notna(rsi_series.iloc[-1]) else 0.0
        four_h_rsi_ok = four_h_rsi > 40.0

        # Confirmation = reversal + RSI only.  Trigger is recorded for
        # transparency but intentionally excluded from the gate because requiring
        # a 4H breakout (close > 3-bar high) is incompatible with the daily
        # WATCH state (which by definition has not yet triggered a breakout).
        four_h_confirmed = four_h_reversal and four_h_rsi_ok

        return {
            "four_h_reversal":      four_h_reversal,
            "four_h_trigger":       four_h_trigger,
            "four_h_rsi":           four_h_rsi,
            "four_h_rsi_ok":        four_h_rsi_ok,
            "four_h_confirmed":     four_h_confirmed,
            "four_h_available":     True,
            "four_h_reversal_name": four_h_reversal_name,
        }

    except Exception:
        return _NEUTRAL_4H.copy()


def analyze_ticker(
    df: pd.DataFrame,
    symbol: str,
    price: float,
    weekly_price_list: list[dict] | None = None,
    *,
    hourly_df: pd.DataFrame | None = None,
    entry_score_threshold: int | None = None,
    watch_score_threshold: int | None = None,
    min_rr_ratio: float | None = None,
    require_weekly_aligned: bool | None = None,
    min_support_strength: str | None = None,
) -> dict:
    """Orchestrator: compute all signals and return full analysis dict.

    Optional threshold kwargs are used by the backtester; when omitted, defaults
    (70, 55, 1.5, True, None) apply in compute_swing_setup_pullback.
    """
    # 200 bars is the hard minimum: SMA-200 requires exactly 200 points, and the
    # BB-squeeze check (compute_volatility_signals) compares the current BB width
    # against its 120-day range, which itself sits on top of a 20-bar BB window.
    # Feeding fewer bars would silently produce None/NaN for those signals.
    if len(df) < 200:
        raise ValueError(f"Insufficient data for {symbol}: need at least 200 bars, got {len(df)}")

    trend = compute_trend_signals(df)
    momentum = compute_momentum_signals(df)
    volatility = compute_volatility_signals(df)
    volume = compute_volume_signals(df)
    sr = compute_support_resistance(df)
    candlestick = compute_candlestick_patterns(df, sr)

    # Weekly trend — best-effort; falls back to neutral if data is missing
    weekly_trend: dict = _NEUTRAL_WEEKLY_TREND.copy()
    try:
        if weekly_price_list:
            weekly_df = _prepare_dataframe(weekly_price_list)
            weekly_trend = compute_weekly_trend(weekly_df)
    except Exception:
        pass  # keep neutral default

    swing_setup = None
    try:
        kwargs: dict = {}
        if entry_score_threshold is not None:
            kwargs["entry_score_threshold"] = entry_score_threshold
        if watch_score_threshold is not None:
            kwargs["watch_score_threshold"] = watch_score_threshold
        if min_rr_ratio is not None:
            kwargs["min_rr_ratio"] = min_rr_ratio
        if require_weekly_aligned is not None:
            kwargs["require_weekly_aligned"] = require_weekly_aligned
        if min_support_strength is not None:
            kwargs["min_support_strength"] = min_support_strength
        swing_setup = compute_swing_setup_pullback(
            df, trend, momentum, volatility, volume, sr, weekly_trend, **kwargs
        )
    except Exception:
        pass  # swing_setup stays None; never breaks the rest of the analysis

    # ── 4H confirmation layer ─────────────────────────────────────────────────
    # 4H can only upgrade WATCH → ENTRY; it never downgrades anything.
    # ALL original risk-management gates must still pass — 4H only confirms
    # timing and cannot override score, R:R, or support-strength thresholds.
    four_h = compute_4h_confirmation(hourly_df)
    four_h_upgrade = False
    _entry_threshold = entry_score_threshold if entry_score_threshold is not None else 70
    _min_rr        = min_rr_ratio        if min_rr_ratio        is not None else 1.5
    _min_support   = min_support_strength if min_support_strength is not None else None
    if swing_setup is not None and swing_setup.get("verdict") == "WATCH":
        _conditions  = swing_setup.get("conditions", {})
        score_ok     = int(swing_setup.get("setup_score") or 0) >= _entry_threshold
        rr_ok        = (_conditions.get("rr_ratio") or 0) >= _min_rr
        support_ok   = _support_strength_meets_minimum(
                           _conditions.get("support_strength"), _min_support
                       )
        if four_h["four_h_confirmed"] and score_ok and rr_ok and support_ok:
            swing_setup["verdict"] = "ENTRY"
            four_h_upgrade = True

    return {
        "ticker": symbol,
        "price": price,
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility,
        "volume": volume,
        "support_resistance": sr,
        "candlestick": candlestick,
        "swing_setup": swing_setup,
        "weekly_trend": weekly_trend,
        "four_h_confirmation": four_h,
        "four_h_upgrade": four_h_upgrade,
    }
