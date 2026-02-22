import numpy as np
import pandas as pd
import talib
from scipy.signal import argrelextrema
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator


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


def compute_support_resistance(df: pd.DataFrame) -> dict:
    """52w high/low, swing highs/lows via scipy argrelextrema."""
    close = df["close"]
    price = close.iloc[-1]

    # 52-week (252 trading days) high/low
    lookback_252 = min(len(df), 252)
    recent = df.iloc[-lookback_252:]
    high_52w = float(recent["high"].max())
    low_52w = float(recent["low"].min())

    dist_from_52w_high = round((price - high_52w) / high_52w * 100, 2)
    dist_from_52w_low = round((price - low_52w) / low_52w * 100, 2)

    # Swing highs/lows from last 90 trading days
    lookback_90 = min(len(df), 90)
    recent_90 = df.iloc[-lookback_90:]

    order = 5  # number of bars on each side
    swing_high_idx = argrelextrema(recent_90["high"].values, np.greater_equal, order=order)[0]
    swing_low_idx = argrelextrema(recent_90["low"].values, np.less_equal, order=order)[0]

    swing_highs = sorted(set(round(float(recent_90["high"].iloc[i]), 2) for i in swing_high_idx), reverse=True)
    swing_lows = sorted(set(round(float(recent_90["low"].iloc[i]), 2) for i in swing_low_idx))

    # Nearest resistance (swing high above price) and support (swing low below price)
    resistances = [s for s in swing_highs if s > price]
    supports = [s for s in swing_lows if s < price]

    nearest_resistance = min(resistances) if resistances else high_52w
    nearest_support = max(supports) if supports else low_52w

    dist_to_resistance = round((nearest_resistance - price) / price * 100, 2)
    dist_to_support = round((price - nearest_support) / price * 100, 2)

    return {
        "high_52w": high_52w,
        "low_52w": low_52w,
        "distance_from_52w_high_pct": dist_from_52w_high,
        "distance_from_52w_low_pct": dist_from_52w_low,
        "swing_highs": swing_highs[:5],
        "swing_lows": swing_lows[:5],
        "nearest_resistance": nearest_resistance,
        "nearest_support": nearest_support,
        "distance_to_resistance_pct": dist_to_resistance,
        "distance_to_support_pct": dist_to_support,
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

    # Get all TA-Lib candlestick pattern functions (CDL*)
    candle_funcs = talib.get_function_groups()["Pattern Recognition"]

    patterns = []
    for func_name in candle_funcs:
        func = getattr(talib, func_name)
        result = func(o, h, l, c)
        last_val = int(result[-1])
        if last_val != 0:
            pattern_name = func_name.replace("CDL", "").lower()
            pattern_type = "bullish" if last_val > 0 else "bearish"
            patterns.append({
                "pattern": pattern_name,
                "pattern_type": pattern_type,
                "at_support": at_support,
                "at_resistance": at_resistance,
                "significance": significance,
            })

    return patterns


def analyze_ticker(df: pd.DataFrame, symbol: str, price: float) -> dict:
    """Orchestrator: compute all signals and return full analysis dict."""
    if len(df) < 50:
        raise ValueError(f"Insufficient data for {symbol}: need at least 50 bars, got {len(df)}")

    trend = compute_trend_signals(df)
    momentum = compute_momentum_signals(df)
    volatility = compute_volatility_signals(df)
    volume = compute_volume_signals(df)
    sr = compute_support_resistance(df)
    candlestick = compute_candlestick_patterns(df, sr)

    return {
        "ticker": symbol,
        "price": price,
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility,
        "volume": volume,
        "support_resistance": sr,
        "candlestick": candlestick,
    }
