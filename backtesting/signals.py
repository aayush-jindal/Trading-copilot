"""
SignalSnapshot dataclass + SignalEngine.

Wraps app/services/ta_engine.py in a read-only relationship.
Calls ta_engine functions directly — never reimplements any signal logic.
"""

from dataclasses import dataclass, field

import pandas as pd

from app.services.ta_engine import (
    compute_candlestick_patterns,
    compute_momentum_signals,
    compute_support_resistance,
    compute_swing_setup_pullback,
    compute_trend_signals,
    compute_volatility_signals,
    compute_volume_signals,
    compute_weekly_trend,
    _NEUTRAL_WEEKLY_TREND,
)


@dataclass
class SignalSnapshot:
    price: float
    trend: dict
    momentum: dict
    volatility: dict
    volume: dict
    support_resistance: dict
    swing_setup: dict | None
    weekly: dict | None
    candlestick: list = field(default_factory=list)


class SignalEngine:
    """Compute all TA signals for a single bar (the last row of df).

    Args:
        df: Daily OHLCV DataFrame with DatetimeIndex (open/high/low/close/volume).
            Must have at least 200 rows — same requirement as ta_engine.analyze_ticker.
        weekly_df: Optional weekly OHLCV DataFrame for weekly trend computation.
            If None, weekly field of the snapshot will be _NEUTRAL_WEEKLY_TREND.

    Returns:
        SignalSnapshot with all signal dicts populated.
    """

    def compute(self, df: pd.DataFrame, weekly_df: pd.DataFrame | None = None) -> SignalSnapshot:
        price = float(df["close"].iloc[-1])

        trend       = compute_trend_signals(df)
        momentum    = compute_momentum_signals(df)
        volatility  = compute_volatility_signals(df)
        volume      = compute_volume_signals(df)
        sr          = compute_support_resistance(df)
        candlestick = compute_candlestick_patterns(df, sr)

        weekly: dict | None = None
        if weekly_df is not None and len(weekly_df) >= 42:
            try:
                weekly = compute_weekly_trend(weekly_df)
            except Exception:
                weekly = _NEUTRAL_WEEKLY_TREND.copy()
        else:
            weekly = _NEUTRAL_WEEKLY_TREND.copy()

        swing_setup = None
        try:
            swing_setup = compute_swing_setup_pullback(
                df, trend, momentum, volatility, volume, sr, weekly
            )
        except Exception:
            pass

        return SignalSnapshot(
            price=price,
            trend=trend,
            momentum=momentum,
            volatility=volatility,
            volume=volume,
            support_resistance=sr,
            swing_setup=swing_setup,
            weekly=weekly,
            candlestick=candlestick,
        )
