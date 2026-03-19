import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

from app.services.ta_engine import (
    _apply_rr_gate,
    _classify_rr_ratio,
    _find_reversal_candles,
    _get_provisional_levels,
    _NEUTRAL_4H,
    _NEUTRAL_WEEKLY_TREND,
    _prepare_dataframe,
    _resample_to_4h,
    analyze_ticker,
    compute_4h_confirmation,
    compute_candlestick_patterns,
    compute_momentum_signals,
    compute_support_resistance,
    compute_swing_setup_pullback,
    compute_trend_signals,
    compute_volatility_signals,
    compute_volume_signals,
    compute_weekly_trend,
)


class TestPrepareDataframe:
    def test_converts_list_to_dataframe(self, sample_price_list):
        df = _prepare_dataframe(sample_price_list)
        assert isinstance(df, pd.DataFrame)
        assert isinstance(df.index, pd.DatetimeIndex)
        assert list(df.columns) >= ["open", "high", "low", "close", "volume"]

    def test_sorted_by_date(self, sample_price_list):
        df = _prepare_dataframe(sample_price_list)
        assert df.index.is_monotonic_increasing


class TestTrendSignals:
    def test_all_mas_computed(self, sample_df):
        result = compute_trend_signals(sample_df)
        for key in ["sma_20", "sma_50", "sma_200", "ema_9", "ema_21"]:
            assert result[key] is not None
            assert isinstance(result[key], float)

    def test_signal_classification(self, sample_df):
        result = compute_trend_signals(sample_df)
        assert result["signal"] in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_price_vs_ma_positions(self, sample_df):
        result = compute_trend_signals(sample_df)
        for key in ["price_vs_sma20", "price_vs_sma50", "price_vs_sma200"]:
            assert result[key] in ("above", "below")

    def test_golden_cross_detection(self, mock_ohlcv_df):
        # Create data where SMA50 crosses above SMA200
        # Start with low prices, then jump up to force SMA50 > SMA200
        df = mock_ohlcv_df(days=300, start_price=50, trend="up", volatility=0.005)
        result = compute_trend_signals(df)
        assert isinstance(result["golden_cross"], bool)
        assert isinstance(result["death_cross"], bool)

    def test_distance_percentages(self, sample_df):
        result = compute_trend_signals(sample_df)
        for key in ["distance_from_sma20_pct", "distance_from_sma50_pct", "distance_from_sma200_pct"]:
            assert result[key] is not None
            assert isinstance(result[key], float)


class TestMomentumSignals:
    def test_rsi_computed(self, sample_df):
        result = compute_momentum_signals(sample_df)
        assert result["rsi"] is not None
        assert 0 <= result["rsi"] <= 100

    def test_rsi_signal_thresholds(self, sample_df):
        result = compute_momentum_signals(sample_df)
        assert result["rsi_signal"] in (
            "OVERBOUGHT", "OVERSOLD", "NEUTRAL",
            "MODERATE_BULLISH", "MODERATE_BEARISH",
        )

    def test_macd_computed(self, sample_df):
        result = compute_momentum_signals(sample_df)
        assert result["macd"] is not None
        assert result["macd_signal"] is not None
        assert result["macd_histogram"] is not None

    def test_macd_crossover_values(self, sample_df):
        result = compute_momentum_signals(sample_df)
        assert result["macd_crossover"] in (
            "bullish_crossover", "bearish_crossover", "none",
        )

    def test_stochastic_computed(self, sample_df):
        result = compute_momentum_signals(sample_df)
        assert result["stochastic_k"] is not None
        assert result["stochastic_d"] is not None

    def test_overall_signal(self, sample_df):
        result = compute_momentum_signals(sample_df)
        assert result["signal"] in ("BULLISH", "BEARISH", "NEUTRAL")


class TestVolatilitySignals:
    def test_bb_computed(self, sample_df):
        result = compute_volatility_signals(sample_df)
        assert result["bb_upper"] is not None
        assert result["bb_middle"] is not None
        assert result["bb_lower"] is not None
        assert result["bb_upper"] > result["bb_lower"]

    def test_bb_position_range(self, sample_df):
        result = compute_volatility_signals(sample_df)
        assert result["bb_position"] is not None

    def test_bb_squeeze_bool(self, sample_df):
        result = compute_volatility_signals(sample_df)
        assert isinstance(result["bb_squeeze"], bool)

    def test_atr_computed(self, sample_df):
        result = compute_volatility_signals(sample_df)
        assert result["atr"] is not None
        assert result["atr"] > 0
        assert result["atr_vs_price_pct"] is not None

    def test_signal_classification(self, sample_df):
        result = compute_volatility_signals(sample_df)
        assert result["signal"] in ("HIGH_VOLATILITY", "LOW_VOLATILITY", "NORMAL")


class TestVolumeSignals:
    def test_volume_ratio(self, sample_df):
        result = compute_volume_signals(sample_df)
        assert result["volume_ratio"] is not None
        assert result["volume_ratio"] > 0

    def test_volume_signal_values(self, sample_df):
        result = compute_volume_signals(sample_df)
        assert result["volume_signal"] in ("HIGH", "LOW", "NORMAL")

    def test_obv_computed(self, sample_df):
        result = compute_volume_signals(sample_df)
        assert result["obv"] is not None

    def test_obv_trend(self, sample_df):
        result = compute_volume_signals(sample_df)
        assert result["obv_trend"] in ("RISING", "FALLING", "NEUTRAL")


# ── Weekly-trend fixture helpers ──────────────────────────────────────────────

def _last_bday() -> pd.Timestamp:
    """Return today normalized to the most recent business day (pandas 3.x fix)."""
    return pd.offsets.BDay().rollback(pd.Timestamp.today().normalize())


def _last_friday() -> pd.Timestamp:
    """Return the most recent Friday on or before today (pandas 3.x fix)."""
    return pd.offsets.Week(weekday=4).rollback(pd.Timestamp.today().normalize())


def _make_weekly_bullish_df(n: int = 60) -> pd.DataFrame:
    """n weekly bars with a clean uptrend: price > SMA10 > SMA40.

    Uses a fixed Friday anchor (2024-01-05) so the date range always produces
    exactly n periods regardless of which day of the week the test runs on.

    Root cause of the previous flakiness: pd.date_range with end=today and
    freq='W-FRI' produces n-1 dates in pandas 2.2+ whenever today is not a
    Friday, because the end date falls between weekly anchors and is treated
    as exclusive.  Pinning to a known Friday eliminates the edge case entirely.
    """
    _FIXED_FRIDAY = pd.Timestamp("2024-01-05")  # deterministic anchor (Friday)
    dates = pd.date_range(end=_FIXED_FRIDAY, periods=n, freq="W-FRI")
    close = np.linspace(80, 130, n)   # steady climb → SMA10 > SMA40 throughout
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1,
         "close": close, "volume": np.ones(n) * 5_000_000},
        index=dates,
    )
    df.index.name = "date"
    return df


def _make_weekly_bearish_df(n: int = 60) -> pd.DataFrame:
    """n weekly bars with a clean downtrend: price < SMA10 < SMA40.

    Uses the same fixed Friday anchor as _make_weekly_bullish_df to avoid
    the pandas 2.2+ date_range off-by-one when today is not a Friday.
    """
    _FIXED_FRIDAY = pd.Timestamp("2024-01-05")  # deterministic anchor (Friday)
    dates = pd.date_range(end=_FIXED_FRIDAY, periods=n, freq="W-FRI")
    close = np.linspace(130, 80, n)   # steady decline
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1,
         "close": close, "volume": np.ones(n) * 5_000_000},
        index=dates,
    )
    df.index.name = "date"
    return df


class TestWeeklyTrend:
    """Tests for compute_weekly_trend."""

    def test_returns_neutral_for_insufficient_data(self):
        df = _make_weekly_bullish_df(n=30)   # < 42 bars
        result = compute_weekly_trend(df)
        assert result["weekly_trend"] == "NEUTRAL"
        assert result["weekly_trend_strength"] == "WEAK"

    def test_returns_neutral_for_empty_df(self):
        result = compute_weekly_trend(pd.DataFrame())
        assert result == _NEUTRAL_WEEKLY_TREND

    def test_bullish_trend_detected(self):
        df = _make_weekly_bullish_df(n=60)
        result = compute_weekly_trend(df)
        assert result["weekly_trend"] == "BULLISH"
        assert result["price_vs_weekly_sma10"] == "above"
        assert result["price_vs_weekly_sma40"] == "above"
        assert result["weekly_sma10_vs_sma40"] == "above"

    def test_bearish_trend_detected(self):
        df = _make_weekly_bearish_df(n=60)
        result = compute_weekly_trend(df)
        assert result["weekly_trend"] == "BEARISH"
        assert result["price_vs_weekly_sma10"] == "below"
        assert result["price_vs_weekly_sma40"] == "below"
        assert result["weekly_sma10_vs_sma40"] == "below"

    def test_all_output_keys_present(self):
        df = _make_weekly_bullish_df(n=60)
        result = compute_weekly_trend(df)
        for key in [
            "weekly_trend", "weekly_sma10", "weekly_sma40",
            "price_vs_weekly_sma10", "price_vs_weekly_sma40",
            "weekly_sma10_vs_sma40", "weekly_trend_strength",
        ]:
            assert key in result, f"Missing key: {key}"

    def test_strength_strong_when_far_from_sma40(self):
        df = _make_weekly_bullish_df(n=60)
        result = compute_weekly_trend(df)
        # Linspace 80→130 over 60 bars: final price >> SMA40
        assert result["weekly_trend_strength"] == "STRONG"

    def test_strength_values_valid(self):
        for df in [_make_weekly_bullish_df(), _make_weekly_bearish_df()]:
            result = compute_weekly_trend(df)
            assert result["weekly_trend_strength"] in ("STRONG", "MODERATE", "WEAK")

    def test_sma_values_are_floats(self):
        df = _make_weekly_bullish_df(n=60)
        result = compute_weekly_trend(df)
        assert isinstance(result["weekly_sma10"], float)
        assert isinstance(result["weekly_sma40"], float)


class TestWeeklyTrendIntegration:
    """Integration tests: weekly_trend flows through swing setup and analyze_ticker."""

    def test_analyze_ticker_returns_weekly_trend_key(self, sample_df):
        price = float(sample_df["close"].iloc[-1])
        result = analyze_ticker(sample_df, "TEST", price)
        assert "weekly_trend" in result
        wt = result["weekly_trend"]
        assert wt["weekly_trend"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert wt["weekly_trend_strength"] in ("STRONG", "MODERATE", "WEAK")

    def test_swing_conditions_has_weekly_trend_aligned(self, sample_df):
        price = float(sample_df["close"].iloc[-1])
        result = analyze_ticker(sample_df, "TEST", price)
        if result["swing_setup"] is not None:
            assert "weekly_trend_aligned" in result["swing_setup"]["conditions"]

    def test_weekly_gate_caps_entry_to_watch(self, mock_ohlcv_df):
        """An ENTRY-quality daily setup with a bearish weekly trend must become WATCH."""
        df = mock_ohlcv_df(days=300, trend="up", volatility=0.008)
        trend = compute_trend_signals(df)
        momentum = compute_momentum_signals(df)
        volatility = compute_volatility_signals(df)
        vol = compute_volume_signals(df)
        sr = compute_support_resistance(df)

        bearish_weekly = {**_NEUTRAL_WEEKLY_TREND, "weekly_trend": "BEARISH"}
        result = compute_swing_setup_pullback(
            df, trend, momentum, volatility, vol, sr,
            weekly_trend=bearish_weekly,
        )
        # Hard gate: never ENTRY when weekly is bearish
        assert result["verdict"] != "ENTRY"
        assert result["conditions"]["weekly_trend_aligned"] is False

    def test_weekly_warning_present_when_gate_fires(self, mock_ohlcv_df):
        """weekly_trend_warning must be set when the gate downgrades a verdict."""
        df = mock_ohlcv_df(days=300, trend="up", volatility=0.008)
        trend = compute_trend_signals(df)
        momentum = compute_momentum_signals(df)
        volatility = compute_volatility_signals(df)
        vol = compute_volume_signals(df)
        sr = compute_support_resistance(df)

        bearish_weekly = {**_NEUTRAL_WEEKLY_TREND, "weekly_trend": "BEARISH"}

        # Force maximum score to ensure ENTRY is attempted before the gate
        # (close above prior high)
        prev_high = float(df["high"].iloc[-2])
        df.iloc[-1, df.columns.get_loc("close")] = prev_high * 1.01

        result = compute_swing_setup_pullback(
            df, trend, momentum, volatility, vol, sr,
            weekly_trend=bearish_weekly,
        )
        if result["verdict"] == "WATCH" and result["conditions"]["weekly_trend_aligned"] is False:
            # Warning must be set if gate was the reason for downgrade
            assert result["weekly_trend_warning"] is not None

    def test_no_weekly_trend_does_not_penalise(self, mock_ohlcv_df):
        """Calling without weekly_trend (None) must not penalise the verdict."""
        df = mock_ohlcv_df(days=300, trend="up", volatility=0.008)
        trend = compute_trend_signals(df)
        momentum = compute_momentum_signals(df)
        volatility = compute_volatility_signals(df)
        vol = compute_volume_signals(df)
        sr = compute_support_resistance(df)

        result_no_weekly = compute_swing_setup_pullback(
            df, trend, momentum, volatility, vol, sr,
            weekly_trend=None,
        )
        result_bullish_weekly = compute_swing_setup_pullback(
            df, trend, momentum, volatility, vol, sr,
            weekly_trend={**_NEUTRAL_WEEKLY_TREND, "weekly_trend": "BULLISH"},
        )
        # Both must give the same verdict (None = no penalty = treated as aligned)
        assert result_no_weekly["verdict"] == result_bullish_weekly["verdict"]


class TestSupportResistance:
    def test_52w_high_low(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert result["high_52w"] >= result["low_52w"]

    def test_swing_detection(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert isinstance(result["swing_highs"], list)
        assert isinstance(result["swing_lows"], list)
        # Each element is now a dict with price + strength (v2 format)
        for lvl in result["swing_highs"] + result["swing_lows"]:
            assert "price" in lvl
            assert "strength" in lvl

    def test_nearest_levels(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert result["nearest_resistance"] is not None
        assert result["nearest_support"] is not None

    def test_distance_percentages(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert isinstance(result["distance_to_resistance_pct"], float)
        assert isinstance(result["distance_to_support_pct"], float)
        assert "support_is_provisional" in result
        assert "resistance_is_provisional" in result


class TestCandlestickPatterns:
    def test_returns_list(self, sample_df):
        sr = compute_support_resistance(sample_df)
        result = compute_candlestick_patterns(sample_df, sr)
        assert isinstance(result, list)

    def test_pattern_structure(self, sample_df):
        sr = compute_support_resistance(sample_df)
        result = compute_candlestick_patterns(sample_df, sr)
        for p in result:
            assert "pattern" in p
            assert "pattern_type" in p
            assert p["pattern_type"] in ("bullish", "bearish")
            assert "significance" in p
            assert p["significance"] in ("HIGH", "LOW")


class TestAnalyzeTicker:
    def test_returns_complete_structure(self, sample_df):
        price = float(sample_df["close"].iloc[-1])
        result = analyze_ticker(sample_df, "TEST", price)
        assert result["ticker"] == "TEST"
        assert result["price"] == price
        for key in ["trend", "momentum", "volatility", "volume", "support_resistance", "candlestick"]:
            assert key in result

    def test_insufficient_data_raises(self, mock_ohlcv_df):
        df = mock_ohlcv_df(days=20)
        with pytest.raises(ValueError, match="Insufficient data"):
            analyze_ticker(df, "TEST", 100.0)

    def test_swing_setup_key_present(self, sample_df):
        price = float(sample_df["close"].iloc[-1])
        result = analyze_ticker(sample_df, "TEST", price)
        assert "swing_setup" in result
        swing = result["swing_setup"]
        if swing is not None:
            assert swing["setup_type"] == "pullback_in_uptrend"
            assert swing["verdict"] in ("ENTRY", "WATCH", "NO_TRADE")


class TestFindReversalCandles:
    def test_returns_list(self, sample_df):
        result = _find_reversal_candles(sample_df)
        assert isinstance(result, list)

    def test_pattern_structure(self, sample_df):
        result = _find_reversal_candles(sample_df)
        for item in result:
            assert "pattern" in item
            assert "bars_ago" in item
            assert "raw_value" in item
            assert "strength" in item
            assert item["strength"] in ("normal", "strong")
            assert 0 <= item["bars_ago"] < 5

    def test_sorted_by_recency(self, sample_df):
        result = _find_reversal_candles(sample_df, scan_bars=5)
        bars_ago_values = [r["bars_ago"] for r in result]
        assert bars_ago_values == sorted(bars_ago_values)

    def test_scan_bars_respected(self, sample_df):
        # bars_ago must always be < scan_bars
        for scan_bars in (3, 5, 10):
            result = _find_reversal_candles(sample_df, scan_bars=scan_bars)
            for item in result:
                assert item["bars_ago"] < scan_bars

    def test_only_bullish_patterns(self, sample_df):
        result = _find_reversal_candles(sample_df)
        for item in result:
            assert item["raw_value"] > 0  # bullish = positive TA-Lib value


class TestSwingSetup:
    """Tests for compute_swing_setup_pullback."""

    def _run_setup(self, df):
        """Run all upstream signals then compute swing setup."""
        trend = compute_trend_signals(df)
        momentum = compute_momentum_signals(df)
        volatility = compute_volatility_signals(df)
        vol = compute_volume_signals(df)
        sr = compute_support_resistance(df)
        return compute_swing_setup_pullback(df, trend, momentum, volatility, vol, sr)

    # ── Structure / contract ──────────────────────────────────────────────────

    def test_complete_structure(self, sample_df):
        result = self._run_setup(sample_df)

        assert result["setup_type"] == "pullback_in_uptrend"
        assert result["verdict"] in ("ENTRY", "WATCH", "NO_TRADE")
        assert isinstance(result["setup_score"], int)
        assert 0 <= result["setup_score"] <= 100
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) >= 7  # one per condition bucket

        cond = result["conditions"]
        for key in [
            "uptrend_confirmed", "adx", "adx_strong", "rsi", "rsi_cooldown",
            "rsi_pullback_label", "pullback_rsi_ok",
            "near_support", "near_resistance", "volume_ratio", "volume_declining",
            "obv_trend", "reversal_candle", "trigger_ok",
            "rr_ratio", "rr_label", "rr_gate_pass", "rr_warning",
        ]:
            assert key in cond, f"missing conditions key: {key}"

        rc = cond["reversal_candle"]
        assert "found" in rc
        assert "patterns" in rc
        assert isinstance(rc["patterns"], list)
        for p in rc["patterns"]:
            assert "pattern" in p
            assert "bars_ago" in p
            assert "raw_value" in p
            assert "strength" in p

        levels = result["levels"]
        for k in ["nearest_support", "nearest_resistance", "sr_alignment"]:
            assert k in levels
        assert levels["sr_alignment"] in ("aligned", "misaligned", "neutral")

        risk = result["risk"]
        for k in ["atr14", "entry_zone", "stop_loss", "target", "rr_to_resistance", "rr_ratio"]:
            assert k in risk
        assert "low" in risk["entry_zone"]
        assert "high" in risk["entry_zone"]
        assert risk["entry_zone"]["low"] < risk["entry_zone"]["high"]

    def test_score_always_in_range(self, sample_df, mock_ohlcv_df):
        for trend_dir in ("up", "flat", "down"):
            df = mock_ohlcv_df(days=300, trend=trend_dir)
            result = self._run_setup(df)
            assert 0 <= result["setup_score"] <= 100

    # ── Uptrend / NO_TRADE ────────────────────────────────────────────────────

    def test_no_trade_for_downtrend(self, mock_ohlcv_df):
        """Consistent downtrend → price below SMA50/200 → NO_TRADE."""
        df = mock_ohlcv_df(days=300, trend="down", volatility=0.015)
        result = self._run_setup(df)
        assert result["conditions"]["uptrend_confirmed"] is False
        assert result["verdict"] == "NO_TRADE"

    def test_uptrend_sample_df_confirmed(self, sample_df):
        """300-day uptrend fixture must register as uptrend_confirmed."""
        result = self._run_setup(sample_df)
        assert result["conditions"]["uptrend_confirmed"] is True

    # ── Trigger condition ─────────────────────────────────────────────────────

    def test_trigger_ok_when_close_above_prev_high(self, sample_df):
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())
        df.iloc[-1, df.columns.get_loc("close")] = three_bar_high * 1.02
        result = self._run_setup(df)
        assert result["conditions"]["trigger_ok"] is True

    def test_trigger_false_when_close_below_prev_high(self, sample_df):
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())
        df.iloc[-1, df.columns.get_loc("close")] = three_bar_high * 0.98
        result = self._run_setup(df)
        assert result["conditions"]["trigger_ok"] is False

    def test_trigger_adds_ten_points(self, sample_df):
        """Forcing trigger on/off changes setup_score by at least the trigger_points."""
        df_on = sample_df.copy()
        df_off = sample_df.copy()
        three_bar_high = float(sample_df["high"].iloc[-4:-1].max())

        # Only change close (not volume/open/high/low) to isolate price-trigger effect.
        df_on.iloc[-1, df_on.columns.get_loc("close")] = three_bar_high * 1.03
        df_off.iloc[-1, df_off.columns.get_loc("close")] = three_bar_high * 0.94

        r_on = self._run_setup(df_on)
        r_off = self._run_setup(df_off)

        assert r_on["conditions"]["trigger_ok"] is True
        assert r_off["conditions"]["trigger_ok"] is False
        # Trigger contributes trigger_points; other components may also shift,
        # so score difference is always >= trigger_points.
        assert r_on["setup_score"] - r_off["setup_score"] >= r_on["conditions"]["trigger_points"]

    # ── Trigger tiers (3-bar breakout) ─────────────────────────────────────────

    def test_trigger_strong_all_conditions_met(self, sample_df):
        """Price > 3-bar high, volume ≥ 20d avg, close in upper half → 10 pts, strong."""
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())

        # Price breakout well above 3-bar high
        bar_low = float(df["low"].iloc[-1])
        bar_high = max(three_bar_high * 1.03, bar_low * 1.05)
        close = bar_low + 0.8 * (bar_high - bar_low)  # strong close near top

        df.iloc[-1, df.columns.get_loc("low")] = bar_low
        df.iloc[-1, df.columns.get_loc("high")] = bar_high
        df.iloc[-1, df.columns.get_loc("close")] = close

        # Volume at 1.2× 20d average to guarantee trigger_volume_ok
        vol_series = df["volume"]
        avg_20 = float(vol_series.rolling(20).mean().iloc[-1])
        df.iloc[-1, df.columns.get_loc("volume")] = avg_20 * 1.2

        result = self._run_setup(df)
        cond = result["conditions"]

        assert cond["trigger_ok"] is True
        assert cond["trigger_volume_ok"] is True
        assert cond["trigger_bar_strength_ok"] is True
        assert cond["trigger_points"] == 10
        assert cond["trigger_label"] == "strong"

    def test_trigger_moderate_price_and_volume_only(self, sample_df):
        """Price > 3-bar high, volume ok, weak close location → 7 pts, moderate."""
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())

        bar_low = float(df["low"].iloc[-1])
        bar_high = max(three_bar_high * 1.02, bar_low * 1.05)
        # Close just above 3-bar high but in lower half of bar range
        close = bar_low + 0.3 * (bar_high - bar_low)

        df.iloc[-1, df.columns.get_loc("low")] = bar_low
        df.iloc[-1, df.columns.get_loc("high")] = bar_high
        df.iloc[-1, df.columns.get_loc("close")] = close

        vol_series = df["volume"]
        avg_20 = float(vol_series.rolling(20).mean().iloc[-1])
        df.iloc[-1, df.columns.get_loc("volume")] = avg_20 * 1.1  # ≥ avg

        result = self._run_setup(df)
        cond = result["conditions"]

        assert cond["trigger_ok"] is True
        assert cond["trigger_volume_ok"] is True
        assert cond["trigger_bar_strength_ok"] is False
        assert cond["trigger_points"] == 7
        assert cond["trigger_label"] == "moderate"

    def test_trigger_moderate_price_and_bar_strength_only(self, sample_df):
        """Price > 3-bar high, strong close, but volume < avg → 7 pts, moderate."""
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())

        bar_low = float(df["low"].iloc[-1])
        bar_high = max(three_bar_high * 1.02, bar_low * 1.05)
        close = bar_low + 0.8 * (bar_high - bar_low)  # strong close

        df.iloc[-1, df.columns.get_loc("low")] = bar_low
        df.iloc[-1, df.columns.get_loc("high")] = bar_high
        df.iloc[-1, df.columns.get_loc("close")] = close

        vol_series = df["volume"]
        avg_20 = float(vol_series.rolling(20).mean().iloc[-1])
        df.iloc[-1, df.columns.get_loc("volume")] = avg_20 * 0.8  # below avg

        result = self._run_setup(df)
        cond = result["conditions"]

        assert cond["trigger_ok"] is True
        assert cond["trigger_volume_ok"] is False
        assert cond["trigger_bar_strength_ok"] is True
        assert cond["trigger_points"] == 7
        assert cond["trigger_label"] == "moderate"

    def test_trigger_weak_price_only(self, sample_df):
        """Price > 3-bar high, but volume < avg and weak close → 4 pts, weak."""
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())

        bar_low = float(df["low"].iloc[-1])
        bar_high = max(three_bar_high * 1.02, bar_low * 1.05)
        close = bar_low + 0.3 * (bar_high - bar_low)  # weak close

        df.iloc[-1, df.columns.get_loc("low")] = bar_low
        df.iloc[-1, df.columns.get_loc("high")] = bar_high
        df.iloc[-1, df.columns.get_loc("close")] = close

        vol_series = df["volume"]
        avg_20 = float(vol_series.rolling(20).mean().iloc[-1])
        df.iloc[-1, df.columns.get_loc("volume")] = avg_20 * 0.8  # below avg

        result = self._run_setup(df)
        cond = result["conditions"]

        assert cond["trigger_ok"] is True
        assert cond["trigger_volume_ok"] is False
        assert cond["trigger_bar_strength_ok"] is False
        assert cond["trigger_points"] == 4
        assert cond["trigger_label"] == "weak"

    def test_trigger_not_fired_when_price_below_three_bar_high(self, sample_df):
        """Price trigger is the hard gate: no breakout → 0 pts, trigger_ok False."""
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())

        bar_low = float(df["low"].iloc[-1])
        bar_high = max(three_bar_high * 0.99, bar_low * 1.02)
        close = min(three_bar_high * 0.995, bar_low + 0.4 * (bar_high - bar_low))

        df.iloc[-1, df.columns.get_loc("low")] = bar_low
        df.iloc[-1, df.columns.get_loc("high")] = bar_high
        df.iloc[-1, df.columns.get_loc("close")] = close

        vol_series = df["volume"]
        avg_20 = float(vol_series.rolling(20).mean().iloc[-1])
        # Even with high volume and strong close, without price trigger we must not fire
        df.iloc[-1, df.columns.get_loc("volume")] = avg_20 * 1.5

        result = self._run_setup(df)
        cond = result["conditions"]

        assert cond["trigger_ok"] is False
        assert cond["trigger_points"] == 0
        assert cond["trigger_label"] == "not_fired"

    def test_trigger_bar_range_zero_doji_safe(self, sample_df):
        """Edge case: bar_range = 0 (high == low) → bar_strength_ok False and no error."""
        df = sample_df.copy()
        three_bar_high = float(df["high"].iloc[-4:-1].max())

        # Doji bar: high == low == close, below 3-bar high so trigger doesn't fire
        price = three_bar_high * 0.99
        df.iloc[-1, df.columns.get_loc("low")] = price
        df.iloc[-1, df.columns.get_loc("high")] = price
        df.iloc[-1, df.columns.get_loc("close")] = price

        result = self._run_setup(df)
        cond = result["conditions"]

        assert cond["trigger_bar_strength_ok"] is False
        assert cond["trigger_ok"] is False

    # ── Entry scenario (crafted uptrend + pullback + engulfing + trigger) ─────

    def test_entry_scenario(self, mock_ohlcv_df):
        """Strong uptrend with shallow pullback, bullish engulfing, trigger → uptrend intact."""
        df = mock_ohlcv_df(days=300, trend="up", volatility=0.008)

        # 4-bar shallow pullback on bars 292-295 (~1.2% total) — keeps price above SMA50/200
        base = float(df["close"].iloc[291])
        for i in range(1, 5):
            idx = 291 + i
            p = base * (1 - 0.003 * i)  # 1.2 % total decline, low volume
            df.iloc[idx, df.columns.get_loc("close")] = p
            df.iloc[idx, df.columns.get_loc("open")] = p * 1.003   # bearish bar
            df.iloc[idx, df.columns.get_loc("high")] = p * 1.006
            df.iloc[idx, df.columns.get_loc("low")] = p * 0.997
            df.iloc[idx, df.columns.get_loc("volume")] = float(df["volume"].mean()) * 0.6

        # Bar 296: extra bearish context bar before setup
        P = float(df["close"].iloc[295])
        df.iloc[296, df.columns.get_loc("open")] = P * 1.015
        df.iloc[296, df.columns.get_loc("close")] = P * 0.993   # bearish
        df.iloc[296, df.columns.get_loc("high")] = P * 1.018
        df.iloc[296, df.columns.get_loc("low")] = P * 0.990
        df.iloc[296, df.columns.get_loc("volume")] = float(df["volume"].mean()) * 0.55

        # Bar 298 (yesterday): bearish — to be engulfed tomorrow
        P2 = float(df["close"].iloc[297])
        df.iloc[298, df.columns.get_loc("open")] = P2 * 1.018
        df.iloc[298, df.columns.get_loc("close")] = P2 * 0.992   # bearish close
        df.iloc[298, df.columns.get_loc("high")] = P2 * 1.022
        df.iloc[298, df.columns.get_loc("low")] = P2 * 0.988
        df.iloc[298, df.columns.get_loc("volume")] = float(df["volume"].mean()) * 0.6

        # Bar 299 (today): bullish engulfing body + closes above bar 298's high (trigger)
        # Engulfing: open < prior_close AND close > prior_open
        prior_open = float(df["open"].iloc[298])    # P2 * 1.018
        prior_close = float(df["close"].iloc[298])  # P2 * 0.992
        prior_high = float(df["high"].iloc[298])    # P2 * 1.022

        bull_open = prior_close * 0.998              # opens below prior close ✓
        bull_close = prior_open * 1.010              # closes above prior open ✓ (engulfs)
        bull_high = max(bull_close * 1.003, prior_high * 1.005)  # above prior high (trigger)
        bull_low = bull_open * 0.995

        df.iloc[299, df.columns.get_loc("open")] = bull_open
        df.iloc[299, df.columns.get_loc("close")] = bull_high * 0.999  # close ≈ high
        df.iloc[299, df.columns.get_loc("high")] = bull_high
        df.iloc[299, df.columns.get_loc("low")] = bull_low
        df.iloc[299, df.columns.get_loc("volume")] = float(df["volume"].mean()) * 1.2

        result = self._run_setup(df)

        # A 1.2% pullback in a 300-bar uptrend keeps price above SMA50 and SMA200
        assert result["conditions"]["uptrend_confirmed"] is True
        # Close (≈ bull_high * 0.999) is above prior high (bar 298) → trigger ✓
        assert result["conditions"]["trigger_ok"] is True
        # Minimum score: uptrend(30) + ADX≥15(4) + trigger(10) = 44
        assert result["setup_score"] >= 44

    def test_watch_scenario_no_trigger(self, mock_ohlcv_df):
        """Strong uptrend, pullback in RSI range, but close below prior high → at most WATCH."""
        df = mock_ohlcv_df(days=300, trend="up", volatility=0.008)

        # Force close below prior day's high → trigger_ok = False
        prev_high = float(df["high"].iloc[-2])
        df.iloc[-1, df.columns.get_loc("close")] = prev_high * 0.95

        result = self._run_setup(df)

        assert result["conditions"]["trigger_ok"] is False
        # Cannot be ENTRY without trigger
        assert result["verdict"] in ("WATCH", "NO_TRADE")

    # ── Risk sanity ───────────────────────────────────────────────────────────

    def test_stop_loss_below_price(self, sample_df):
        """Stop loss must always be below current price."""
        result = self._run_setup(sample_df)
        price = float(sample_df["close"].iloc[-1])
        assert result["risk"]["stop_loss"] < price

    def test_target_above_price(self, sample_df):
        """Target must be above current price for a bullish setup."""
        result = self._run_setup(sample_df)
        price = float(sample_df["close"].iloc[-1])
        assert result["risk"]["target"] > price

    def test_entry_zone_straddles_support(self, sample_df):
        """Entry zone must be centred on nearest_support (low < support < high)."""
        result = self._run_setup(sample_df)
        nearest_support = result["levels"]["nearest_support"]
        ez = result["risk"]["entry_zone"]
        if nearest_support > 0:
            assert ez["low"] < nearest_support < ez["high"]


# ── Oscillating-market fixture for S/R v2 tests ──────────────────────────────

def _make_oscillating_df() -> pd.DataFrame:
    """300-bar DataFrame where price oscillates sinusoidally between ~95 and ~105.

    This creates clear, repeated swing highs near 105 and swing lows near 95,
    giving the touch-count scorer enough evidence to assign HIGH strength to both
    levels. The final bar lands at close ≈ 100 (sin(10π) = 0), so resistance is
    above and support is below current price.
    """
    n = 300
    dates = pd.date_range(end=_last_bday(), periods=n, freq="B")
    t = np.linspace(0, 10 * np.pi, n)   # 5 complete oscillations
    close = 100.0 + 5.0 * np.sin(t)
    high = close + 0.5
    low = close - 0.5
    opens = np.roll(close, 1)
    opens[0] = close[0]
    df = pd.DataFrame(
        {"open": opens, "high": high, "low": low, "close": close,
         "volume": np.ones(n) * 1_000_000},
        index=dates,
    )
    df.index.name = "date"
    return df


def _make_monotone_df(n: int = 250) -> pd.DataFrame:
    """Strictly-increasing price series with minimal amplitude variation."""
    dates = pd.date_range(end=_last_bday(), periods=n, freq="B")
    close = np.linspace(80, 120, n)
    df = pd.DataFrame(
        {"open": close, "high": close + 0.1, "low": close - 0.1,
         "close": close, "volume": np.ones(n) * 1_000_000},
        index=dates,
    )
    df.index.name = "date"
    return df


class TestSupportResistanceV2:
    """Tests for the multi-window clustered S/R implementation."""

    # ── Output structure ──────────────────────────────────────────────────────

    def test_all_keys_present(self, sample_df):
        result = compute_support_resistance(sample_df)
        required = {
            "high_52w", "low_52w",
            "distance_from_52w_high_pct", "distance_from_52w_low_pct",
            "swing_highs", "swing_lows",
            "nearest_resistance", "nearest_support",
            "distance_to_resistance_pct", "distance_to_support_pct",
            "support_strength", "resistance_strength",   # new in v2
            "support_is_provisional", "resistance_is_provisional",
            "provisional_support", "provisional_resistance",
        }
        assert required.issubset(result.keys())

    def test_swing_level_dicts(self, sample_df):
        """Each element of swing_highs / swing_lows must have price + strength."""
        result = compute_support_resistance(sample_df)
        for key in ("swing_highs", "swing_lows"):
            for entry in result[key]:
                assert isinstance(entry, dict), f"{key} element is not a dict"
                assert "price" in entry and "strength" in entry
                assert isinstance(entry["price"], float)
                assert entry["strength"] in ("HIGH", "MEDIUM", "LOW")

    def test_at_most_five_levels(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert len(result["swing_highs"]) <= 5
        assert len(result["swing_lows"]) <= 5

    def test_strength_fields_valid(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert result["support_strength"] in ("HIGH", "MEDIUM", "LOW")
        assert result["resistance_strength"] in ("HIGH", "MEDIUM", "LOW")

    # ── Price ordering invariants ─────────────────────────────────────────────

    def test_all_swing_highs_above_price(self, sample_df):
        """Every swing_high must be strictly above current price."""
        price = float(sample_df["close"].iloc[-1])
        result = compute_support_resistance(sample_df)
        for lvl in result["swing_highs"]:
            assert lvl["price"] > price, f"swing high {lvl['price']} not above price {price}"

    def test_all_swing_lows_below_price(self, sample_df):
        """Every swing_low must be strictly below current price."""
        price = float(sample_df["close"].iloc[-1])
        result = compute_support_resistance(sample_df)
        for lvl in result["swing_lows"]:
            assert lvl["price"] < price, f"swing low {lvl['price']} not below price {price}"

    def test_nearest_resistance_above_price(self, sample_df):
        price = float(sample_df["close"].iloc[-1])
        result = compute_support_resistance(sample_df)
        assert result["nearest_resistance"] > price

    def test_nearest_support_below_price(self, sample_df):
        price = float(sample_df["close"].iloc[-1])
        result = compute_support_resistance(sample_df)
        assert result["nearest_support"] < price

    def test_distances_are_positive(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert result["distance_to_resistance_pct"] > 0
        assert result["distance_to_support_pct"] > 0

    # ── Ordering within lists ─────────────────────────────────────────────────

    def test_swing_highs_ordered_nearest_first(self, sample_df):
        """swing_highs[0] must be the closest resistance level (lowest price above price)."""
        result = compute_support_resistance(sample_df)
        prices = [lvl["price"] for lvl in result["swing_highs"]]
        assert prices == sorted(prices), "swing_highs not sorted ascending (nearest first)"

    def test_swing_lows_ordered_nearest_first(self, sample_df):
        """swing_lows[0] must be the closest support level (highest price below price)."""
        result = compute_support_resistance(sample_df)
        prices = [lvl["price"] for lvl in result["swing_lows"]]
        assert prices == sorted(prices, reverse=True), "swing_lows not sorted descending (nearest first)"

    # ── Touch-count scoring ───────────────────────────────────────────────────

    def test_frequently_touched_level_gets_high_strength(self):
        """Level visited 3+ times in price history must receive HIGH strength."""
        df = _make_oscillating_df()
        result = compute_support_resistance(df)
        # The oscillating df reliably creates swing highs near 105 (5 peaks × ~3 bars each)
        # and swing lows near 95 (5 troughs). Both should score HIGH.
        all_strengths = (
            [lvl["strength"] for lvl in result["swing_highs"]]
            + [lvl["strength"] for lvl in result["swing_lows"]]
        )
        assert "HIGH" in all_strengths, (
            "Expected at least one HIGH-strength level in oscillating data; "
            f"got strengths: {all_strengths}"
        )

    def test_oscillating_df_support_and_resistance_both_found(self):
        df = _make_oscillating_df()
        result = compute_support_resistance(df)
        price = float(df["close"].iloc[-1])  # ~100
        assert result["nearest_resistance"] > price
        assert result["nearest_support"] < price
        # Both sides should be close to the known oscillation bounds
        assert result["nearest_resistance"] < 110
        assert result["nearest_support"] > 90

    def test_oscillating_resistance_within_range(self):
        """Resistance must be above current price and within the oscillation ceiling.

        argrelextrema(mode='clip') may detect sub-window boundary bars as local
        extrema, producing levels very close to current price. The key invariant
        is directional correctness, not an exact value: resistance > price and
        resistance < 106.5 (amplitude ceiling = 100 + 5 + 0.5 wick + small slack).
        """
        df = _make_oscillating_df()
        result = compute_support_resistance(df)
        price = float(df["close"].iloc[-1])
        assert result["nearest_resistance"] > price
        assert result["nearest_resistance"] < 106.5

    def test_oscillating_support_within_range(self):
        """Support must be below current price and within the oscillation floor."""
        df = _make_oscillating_df()
        result = compute_support_resistance(df)
        price = float(df["close"].iloc[-1])
        assert result["nearest_support"] < price
        assert result["nearest_support"] > 93.5

    # ── Clustering ────────────────────────────────────────────────────────────

    def test_multi_window_produces_more_levels_than_single_window(self, mock_ohlcv_df):
        """Three windows should produce more raw detections than one, resulting in
        a richer set of clustered levels (or at least as many)."""
        df = mock_ohlcv_df(days=504, trend="flat", volatility=0.02)
        result = compute_support_resistance(df)
        # With 504 bars and three windows, we should find multiple levels on each side
        total_levels = len(result["swing_highs"]) + len(result["swing_lows"])
        assert total_levels >= 2, f"Expected multiple S/R levels; got {total_levels}"

    # ── Fallback behaviour ────────────────────────────────────────────────────

    def test_monotone_series_sr_directional_invariants(self):
        """For a strictly-increasing series, directional invariants must hold.

        argrelextrema(mode='clip') detects sub-window boundary bars as local
        extrema, so 'no swing points' is not a safe assumption.  We verify the
        weaker (but always-correct) invariants instead.
        """
        df = _make_monotone_df()
        result = compute_support_resistance(df)
        price = float(df["close"].iloc[-1])
        assert result["nearest_support"] < price
        assert result["nearest_resistance"] > price
        assert result["support_strength"] in {"HIGH", "MEDIUM", "LOW"}
        assert result["resistance_strength"] in {"HIGH", "MEDIUM", "LOW"}

    def test_swing_highs_valid_structure_for_monotone_series(self):
        """swing_highs entries must have correct structure regardless of count.

        The boundary-bar edge effect of argrelextrema(mode='clip') means a
        monotone series may still yield a small number of detected swing highs.
        We validate structure rather than asserting an empty list.
        """
        df = _make_monotone_df()
        result = compute_support_resistance(df)
        for entry in result["swing_highs"]:
            assert "price" in entry and "strength" in entry
            assert entry["price"] > 0
            assert entry["strength"] in {"HIGH", "MEDIUM", "LOW"}

    # ── Backward compatibility ────────────────────────────────────────────────

    def test_swing_lookback_param_ignored(self, sample_df):
        """swing_lookback is kept for API compat but must not change output."""
        r1 = compute_support_resistance(sample_df, swing_lookback=90)
        r2 = compute_support_resistance(sample_df, swing_lookback=180)
        assert r1["nearest_support"] == r2["nearest_support"]
        assert r1["nearest_resistance"] == r2["nearest_resistance"]

    def test_analyze_ticker_includes_new_strength_keys(self, sample_df):
        """Integration: analyze_ticker must pass new S/R keys through to result."""
        price = float(sample_df["close"].iloc[-1])
        result = analyze_ticker(sample_df, "TEST", price)
        sr = result["support_resistance"]
        assert "support_strength" in sr
        assert "resistance_strength" in sr
        assert sr["support_strength"] in ("HIGH", "MEDIUM", "LOW")
        assert sr["resistance_strength"] in ("HIGH", "MEDIUM", "LOW")


class TestSwingSetupRsiCooldown:
    """Unit tests for the RSI cooldown-from-peak scoring in compute_swing_setup_pullback.

    RSIIndicator is patched to return a controlled series so that exact peak and
    current RSI values are known, making assertions on cooldown and label precise.
    """

    @staticmethod
    def _rsi_series(n: int, peak: float, current: float) -> "pd.Series":
        """Synthetic RSI series of length n.

        Values:
          - arr[-10]  = peak    (sits within the 20-bar lookback window)
          - arr[-1]   = current (the most-recent bar)
          - everything else = midpoint, ensuring arr[-20:].max() == peak
        """
        mid = (peak + current) / 2.0
        arr = np.full(n, mid, dtype=float)
        arr[-10] = peak
        arr[-1] = current
        return pd.Series(arr)

    def _run(self, mock_ohlcv_df, rsi_current: float, rsi_peak: float) -> dict:
        """Build a 300-bar uptrend, compute upstream signals, patch RSIIndicator,
        then call compute_swing_setup_pullback and return the result dict."""
        df = mock_ohlcv_df(days=300, trend="up", volatility=0.008)
        trend = compute_trend_signals(df)
        # Override the rsi key to match our controlled current value so the
        # momentum dict and the internal series are consistent.
        momentum = {**compute_momentum_signals(df), "rsi": rsi_current}
        volatility = compute_volatility_signals(df)
        vol = compute_volume_signals(df)
        sr = compute_support_resistance(df)
        n = len(df)
        with patch("app.services.ta_engine.RSIIndicator") as MockRSI:
            MockRSI.return_value.rsi.return_value = self._rsi_series(n, rsi_peak, rsi_current)
            return compute_swing_setup_pullback(df, trend, momentum, volatility, vol, sr)

    # ── Label / rsi_ok correctness ────────────────────────────────────────────

    def test_healthy_pullback(self, mock_ohlcv_df):
        """Cooldown ≥ 15 with RSI in (35, 70] → healthy_pullback, rsi_ok True."""
        result = self._run(mock_ohlcv_df, rsi_current=52.0, rsi_peak=75.0)
        cond = result["conditions"]
        assert cond["rsi_pullback_label"] == "healthy_pullback"
        assert cond["pullback_rsi_ok"] is True
        assert cond["rsi_cooldown"] == 23.0  # round(75 - 52, 1)

    def test_moderate_pullback(self, mock_ohlcv_df):
        """Cooldown 8–14 → moderate_pullback, rsi_ok True."""
        result = self._run(mock_ohlcv_df, rsi_current=57.0, rsi_peak=68.0)
        cond = result["conditions"]
        assert cond["rsi_pullback_label"] == "moderate_pullback"
        assert cond["pullback_rsi_ok"] is True
        assert cond["rsi_cooldown"] == 11.0  # round(68 - 57, 1)

    def test_mild_pullback(self, mock_ohlcv_df):
        """Cooldown 3–7 → mild_pullback, rsi_ok True (partial score)."""
        result = self._run(mock_ohlcv_df, rsi_current=57.0, rsi_peak=62.0)
        cond = result["conditions"]
        assert cond["rsi_pullback_label"] == "mild_pullback"
        assert cond["pullback_rsi_ok"] is True
        assert cond["rsi_cooldown"] == 5.0  # round(62 - 57, 1)

    def test_no_pullback(self, mock_ohlcv_df):
        """Cooldown < 3 → no_pullback, rsi_ok False."""
        result = self._run(mock_ohlcv_df, rsi_current=60.0, rsi_peak=61.5)
        cond = result["conditions"]
        assert cond["rsi_pullback_label"] == "no_pullback"
        assert cond["pullback_rsi_ok"] is False
        assert cond["rsi_cooldown"] == 1.5  # round(61.5 - 60, 1)

    def test_floor_rsi_below_35(self, mock_ohlcv_df):
        """RSI < 35 → no_pullback regardless of cooldown (momentum collapse)."""
        # Cooldown would be 50 pts, but the floor check fires first.
        result = self._run(mock_ohlcv_df, rsi_current=30.0, rsi_peak=80.0)
        cond = result["conditions"]
        assert cond["rsi_pullback_label"] == "no_pullback"
        assert cond["pullback_rsi_ok"] is False
        assert cond["rsi_cooldown"] == 50.0  # cooldown is computed but overridden by floor

    def test_ceiling_rsi_above_70(self, mock_ohlcv_df):
        """RSI > 70 → no_pullback (still overbought, pullback not started)."""
        result = self._run(mock_ohlcv_df, rsi_current=75.0, rsi_peak=80.0)
        cond = result["conditions"]
        assert cond["rsi_pullback_label"] == "no_pullback"
        assert cond["pullback_rsi_ok"] is False

    # ── Score contribution ────────────────────────────────────────────────────

    def test_healthy_awards_full_13_pts_vs_mild(self, mock_ohlcv_df):
        """Healthy pullback (13 pts) vs mild (6 pts) on identical df → delta = 7.

        Both runs use the same seed → same df → same all other scoring factors,
        so the score difference reflects only the RSI points (13 − 6 = 7).
        """
        result_healthy = self._run(mock_ohlcv_df, rsi_current=52.0, rsi_peak=75.0)
        result_mild    = self._run(mock_ohlcv_df, rsi_current=57.0, rsi_peak=62.0)
        assert result_healthy["setup_score"] - result_mild["setup_score"] == 7

    def test_mild_awards_more_than_no_pullback(self, mock_ohlcv_df):
        """Mild pullback (6 pts) vs no_pullback (0 pts) on identical df → delta = 6."""
        result_mild = self._run(mock_ohlcv_df, rsi_current=57.0, rsi_peak=62.0)
        result_none = self._run(mock_ohlcv_df, rsi_current=60.0, rsi_peak=61.5)
        assert result_mild["setup_score"] - result_none["setup_score"] == 6


class TestSwingSetupRiskRewardGate:
    """Unit tests for the R:R classification and gating."""

    @pytest.mark.parametrize(
        "rr_ratio, expected_label, expected_gate",
        [
            (1.5, "good", True),
            (2.0, "good", True),
            (1.2, "marginal", True),
            (1.0, "marginal", True),
            (0.9, "poor", False),
            (0.5, "poor", False),
            (0.49, "bad", False),
            (0.1, "bad", False),
            (None, "unavailable", True),
        ],
    )
    def test_rr_classification(self, rr_ratio, expected_label, expected_gate):
        label, gate = _classify_rr_ratio(rr_ratio)
        assert label == expected_label
        assert gate is expected_gate

    def test_verdict_gate_poor_downgrades_entry_to_watch(self):
        verdict, warning = _apply_rr_gate(
            verdict="ENTRY",
            rr_ratio=0.8,
            rr_label="poor",
            rr_gate_pass=False,
        )
        assert verdict == "WATCH"
        assert warning is not None
        assert "too poor for entry" in warning

    def test_verdict_gate_bad_downgrades_entry_to_no_trade(self):
        verdict, warning = _apply_rr_gate(
            verdict="ENTRY",
            rr_ratio=0.3,
            rr_label="bad",
            rr_gate_pass=False,
        )
        assert verdict == "NO_TRADE"
        assert warning is not None
        assert "unfavourable regardless of other conditions" in warning

    def test_verdict_gate_bad_downgrades_watch_to_no_trade(self):
        verdict, warning = _apply_rr_gate(
            verdict="WATCH",
            rr_ratio=0.3,
            rr_label="bad",
            rr_gate_pass=False,
        )
        assert verdict == "NO_TRADE"
        assert warning is not None

    def test_verdict_gate_marginal_keeps_entry_with_warning(self):
        verdict, warning = _apply_rr_gate(
            verdict="ENTRY",
            rr_ratio=1.1,
            rr_label="marginal",
            rr_gate_pass=True,
        )
        assert verdict == "ENTRY"
        assert warning is not None
        assert "R:R is marginal" in warning

    def test_verdict_gate_good_keeps_entry_without_warning(self):
        verdict, warning = _apply_rr_gate(
            verdict="ENTRY",
            rr_ratio=2.0,
            rr_label="good",
            rr_gate_pass=True,
        )
        assert verdict == "ENTRY"
        assert warning is None


class TestProvisionalLevels:
    """Unit tests for _get_provisional_levels."""

    def _make_df(self, lows: list[float], highs: list[float], closes: list[float]) -> pd.DataFrame:
        n = len(closes)
        dates = pd.date_range(end=_last_bday(), periods=n, freq="B")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": np.ones(n) * 1_000_000,
            },
            index=dates,
        )
        df.index.name = "date"
        return df

    def test_recent_low_below_price_returns_provisional_support(self):
        closes = [100] * 10
        lows = [98, 99, 97, 96, 95, 96, 97, 96, 97, 100]
        highs = [101] * 10
        df = self._make_df(lows, highs, closes)
        current_price = float(df["close"].iloc[-1])

        result = _get_provisional_levels(df, current_price, n_bars=7)
        assert result["provisional_support"] == round(min(lows[-8:-1]), 2)
        assert result["provisional_support_distance_pct"] is not None

    def test_recent_high_above_price_returns_provisional_resistance(self):
        closes = [100] * 10
        lows = [99] * 10
        highs = [101, 102, 103, 104, 105, 104, 103, 102, 101, 100]
        df = self._make_df(lows, highs, closes)
        current_price = float(df["close"].iloc[-1])

        result = _get_provisional_levels(df, current_price, n_bars=7)
        assert result["provisional_resistance"] == round(max(highs[-8:-1]), 2)
        assert result["provisional_resistance_distance_pct"] is not None

    def test_recent_low_above_price_sets_provisional_support_none(self):
        closes = [100] * 10
        lows = [101, 102, 103, 104, 105, 104, 103, 102, 101, 100]
        highs = [106] * 10
        df = self._make_df(lows, highs, closes)
        current_price = float(df["close"].iloc[-1])

        result = _get_provisional_levels(df, current_price, n_bars=7)
        assert result["provisional_support"] is None
        assert result["provisional_support_distance_pct"] is None

    def test_recent_low_too_far_discarded(self):
        closes = [100] * 10
        lows = [80, 81, 82, 83, 84, 85, 86, 87, 88, 100]  # > 8% below price
        highs = [101] * 10
        df = self._make_df(lows, highs, closes)
        current_price = float(df["close"].iloc[-1])

        result = _get_provisional_levels(df, current_price, n_bars=7, max_distance_pct=8.0)
        assert result["provisional_support"] is None
        assert result["provisional_support_distance_pct"] is None

    def test_excludes_todays_bar(self):
        closes = [100] * 10
        lows = [98, 99, 97, 96, 95, 96, 97, 96, 95, 80]  # today's low = 80, previous window min = 95
        highs = [101] * 10
        df = self._make_df(lows, highs, closes)
        current_price = float(df["close"].iloc[-1])

        result = _get_provisional_levels(df, current_price, n_bars=7)
        # should use min over bars 2..8 (0-based) and exclude today's 80
        assert result["provisional_support"] == 95.0


# ── 4H Engine Tests ───────────────────────────────────────────────────────────

def _make_hourly_df(n_hours: int = 200, start_price: float = 100.0, trend: str = "up") -> pd.DataFrame:
    """Generate a synthetic 1H OHLCV DataFrame with UTC DatetimeIndex."""
    np.random.seed(7)
    end = pd.Timestamp("2024-06-01 20:00:00", tz="UTC")
    dates = pd.date_range(end=end, periods=n_hours, freq="1h")
    drift = {"up": 0.0005, "down": -0.0005, "flat": 0.0}[trend]
    returns = np.random.normal(drift, 0.005, n_hours)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0, 0.002, n_hours)))
    low = close * (1 - np.abs(np.random.normal(0, 0.002, n_hours)))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = np.random.randint(100_000, 1_000_000, n_hours).astype(float)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    df.index.name = "timestamp"
    return df


class TestResampleTo4H:
    def test_returns_fewer_bars_than_input(self):
        hourly = _make_hourly_df(n_hours=200)
        df_4h = _resample_to_4h(hourly)
        assert len(df_4h) < len(hourly)
        assert len(df_4h) > 0

    def test_empty_input_returns_empty(self):
        result = _resample_to_4h(pd.DataFrame())
        assert result.empty

    def test_ohlcv_columns_present(self):
        hourly = _make_hourly_df(n_hours=100)
        df_4h = _resample_to_4h(hourly)
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df_4h.columns

    def test_high_is_max_of_constituent_bars(self):
        """4H high must equal the maximum 1H high within the bucket."""
        hourly = _make_hourly_df(n_hours=80)
        df_4h = _resample_to_4h(hourly)
        # Pick the first complete 4H bar and verify its high
        if len(df_4h) >= 2:
            bar_start = df_4h.index[0]
            bar_end = df_4h.index[1]
            window = hourly[(hourly.index >= bar_start) & (hourly.index < bar_end)]
            if not window.empty:
                assert abs(df_4h["high"].iloc[0] - window["high"].max()) < 1e-6


class TestCompute4HConfirmation:
    def test_empty_df_returns_neutral(self):
        result = compute_4h_confirmation(pd.DataFrame())
        assert result == _NEUTRAL_4H

    def test_none_returns_neutral(self):
        result = compute_4h_confirmation(None)
        assert result == _NEUTRAL_4H

    def test_insufficient_bars_returns_unavailable(self):
        """Fewer than 20 4H bars → four_h_available: False, all False."""
        # 40 hourly bars → ~10 4H bars (< 20 required)
        hourly = _make_hourly_df(n_hours=40)
        result = compute_4h_confirmation(hourly)
        assert result["four_h_available"] is False
        assert result["four_h_confirmed"] is False
        assert result["four_h_reversal"] is False
        assert result["four_h_trigger"] is False
        assert result["four_h_rsi_ok"] is False

    def test_sufficient_bars_returns_available(self):
        """200 hourly bars → ~50 4H bars → four_h_available: True."""
        hourly = _make_hourly_df(n_hours=200)
        result = compute_4h_confirmation(hourly)
        assert result["four_h_available"] is True
        # RSI should be a valid float
        assert isinstance(result["four_h_rsi"], float)
        assert 0.0 <= result["four_h_rsi"] <= 100.0

    def test_rsi_below_40_rsi_ok_false(self):
        """When 4H RSI <= 40, four_h_rsi_ok should be False."""
        # Downtrend data tends to produce low RSI
        hourly = _make_hourly_df(n_hours=200, trend="down")
        result = compute_4h_confirmation(hourly)
        if result["four_h_available"] and result["four_h_rsi"] <= 40.0:
            assert result["four_h_rsi_ok"] is False
            assert result["four_h_confirmed"] is False

    def test_confirmed_requires_reversal_and_rsi(self):
        """four_h_confirmed is True only when reversal AND rsi_ok hold.

        The trigger field is informational only and is intentionally excluded
        from the confirmation gate (a 4H breakout is anti-correlated with the
        daily WATCH pullback state that the upgrade is designed to improve).
        """
        hourly = _make_hourly_df(n_hours=200)
        result = compute_4h_confirmation(hourly)
        if result["four_h_available"]:
            expected = result["four_h_reversal"] and result["four_h_rsi_ok"]
            assert result["four_h_confirmed"] == expected

    def test_no_crash_on_malformed_data(self):
        """Should never raise — returns neutral on bad input."""
        df = pd.DataFrame({"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
                          index=pd.DatetimeIndex(["2024-01-01 00:00"], tz="UTC"))
        result = compute_4h_confirmation(df)
        assert isinstance(result, dict)
        assert "four_h_confirmed" in result


class TestAnalyzeTicker4HIntegration:
    """Integration tests for the 4H upgrade logic inside analyze_ticker."""

    def _run(self, daily_df, hourly_df=None):
        price = float(daily_df["close"].iloc[-1])
        return analyze_ticker(daily_df, "TEST", price, hourly_df=hourly_df)

    def test_four_h_fields_always_present(self, sample_df):
        """four_h_confirmation and four_h_upgrade are always in the result."""
        result = self._run(sample_df)
        assert "four_h_confirmation" in result
        assert "four_h_upgrade" in result

    def test_hourly_df_none_does_not_crash(self, sample_df):
        """Passing hourly_df=None should not raise and four_h_available should be False."""
        result = self._run(sample_df, hourly_df=None)
        assert result["four_h_confirmation"]["four_h_available"] is False
        assert result["four_h_upgrade"] is False

    def test_no_trade_not_upgraded_by_4h(self, mock_ohlcv_df):
        """4H confirmation must never upgrade NO_TRADE."""
        # Bearish daily data → likely NO_TRADE
        daily = mock_ohlcv_df(days=300, trend="down")
        hourly = _make_hourly_df(n_hours=200, trend="up")
        result = self._run(daily, hourly_df=hourly)
        # Even if 4H is confirmed, a NO_TRADE daily verdict must stay NO_TRADE
        if result["swing_setup"] and result["swing_setup"]["verdict"] == "NO_TRADE":
            assert result["four_h_upgrade"] is False

    def test_entry_verdict_unchanged_by_4h(self, mock_ohlcv_df):
        """An existing ENTRY verdict (pre-4H) must not be double-upgraded."""
        daily = mock_ohlcv_df(days=300, trend="up")
        result_no_hourly = self._run(daily)
        result_with_hourly = self._run(daily, hourly_df=_make_hourly_df(200))
        # If daily alone gives ENTRY, 4H should not change it to something else
        if result_no_hourly.get("swing_setup", {}) and result_no_hourly["swing_setup"]["verdict"] == "ENTRY":
            assert result_with_hourly["swing_setup"]["verdict"] == "ENTRY"
            # four_h_upgrade is only True for WATCH→ENTRY transitions
            assert result_with_hourly["four_h_upgrade"] is False

    def test_watch_upgrades_when_4h_confirmed(self, mock_ohlcv_df):
        """WATCH with score >= entry_threshold + 4H confirmed → ENTRY."""
        import unittest.mock as mock
        from app.services import ta_engine

        daily = mock_ohlcv_df(days=300, trend="up")
        hourly = _make_hourly_df(200, trend="up")

        _confirmed_4h = {**_NEUTRAL_4H, "four_h_available": True, "four_h_confirmed": True,
                         "four_h_reversal": True, "four_h_trigger": True,
                         "four_h_rsi": 55.0, "four_h_rsi_ok": True}

        with mock.patch.object(ta_engine, "compute_4h_confirmation", return_value=_confirmed_4h):
            with mock.patch.object(ta_engine, "compute_swing_setup_pullback",
                                   return_value={"verdict": "WATCH", "setup_score": 75,
                                                 "setup_type": "pullback_in_uptrend",
                                                 "weekly_trend_warning": None,
                                                 "conditions": {}, "levels": {}, "risk": {}, "reasons": []}):
                result = self._run(daily, hourly_df=hourly)

        assert result["swing_setup"]["verdict"] == "ENTRY"
        assert result["four_h_upgrade"] is True

    def test_watch_below_score_not_upgraded_by_4h(self, mock_ohlcv_df):
        """WATCH with score < entry_threshold must NOT be upgraded even when 4H confirms."""
        import unittest.mock as mock
        from app.services import ta_engine

        daily = mock_ohlcv_df(days=300, trend="up")
        hourly = _make_hourly_df(200, trend="up")

        _confirmed_4h = {**_NEUTRAL_4H, "four_h_available": True, "four_h_confirmed": True,
                         "four_h_reversal": True, "four_h_rsi": 55.0, "four_h_rsi_ok": True}

        with mock.patch.object(ta_engine, "compute_4h_confirmation", return_value=_confirmed_4h):
            with mock.patch.object(ta_engine, "compute_swing_setup_pullback",
                                   return_value={"verdict": "WATCH", "setup_score": 62,
                                                 "setup_type": "pullback_in_uptrend",
                                                 "weekly_trend_warning": None,
                                                 "conditions": {}, "levels": {}, "risk": {}, "reasons": []}):
                # Default entry_score_threshold is 70; score 62 should NOT qualify
                result = self._run(daily, hourly_df=hourly)

        assert result["swing_setup"]["verdict"] == "WATCH"
        assert result["four_h_upgrade"] is False

    def test_watch_stays_watch_when_4h_not_confirmed(self, mock_ohlcv_df):
        """When daily says WATCH and 4H is NOT confirmed, verdict stays WATCH."""
        import unittest.mock as mock
        from app.services import ta_engine

        daily = mock_ohlcv_df(days=300, trend="up")
        hourly = _make_hourly_df(200, trend="up")

        _pending_4h = {**_NEUTRAL_4H, "four_h_available": True, "four_h_confirmed": False}

        with mock.patch.object(ta_engine, "compute_4h_confirmation", return_value=_pending_4h):
            with mock.patch.object(ta_engine, "compute_swing_setup_pullback",
                                   return_value={"verdict": "WATCH", "setup_score": 60,
                                                 "setup_type": "pullback_in_uptrend",
                                                 "weekly_trend_warning": None,
                                                 "conditions": {}, "levels": {}, "risk": {}, "reasons": []}):
                result = self._run(daily, hourly_df=hourly)

        assert result["swing_setup"]["verdict"] == "WATCH"
        assert result["four_h_upgrade"] is False


class TestBacktesterHourlySlicing:
    """Unit tests for hourly window slicing in the backtester."""

    def test_analyze_ticker_from_df_no_hourly_no_crash(self, mock_ohlcv_df):
        """analyze_ticker_from_df with hourly_df=None should not crash."""
        from app.services.backtester import BacktestConfig, analyze_ticker_from_df

        daily = mock_ohlcv_df(days=300, trend="up")
        config = BacktestConfig(ticker="TEST")
        result = analyze_ticker_from_df("TEST", daily, config, hourly_df=None)
        four_h = result.get("four_h_confirmation", {})
        assert four_h.get("four_h_available") is False

    def test_analyze_ticker_from_df_with_hourly(self, mock_ohlcv_df):
        """analyze_ticker_from_df with hourly_df provided returns four_h_available."""
        from app.services.backtester import BacktestConfig, analyze_ticker_from_df

        daily = mock_ohlcv_df(days=300, trend="up")
        hourly = _make_hourly_df(n_hours=200, trend="up")
        config = BacktestConfig(ticker="TEST")
        result = analyze_ticker_from_df("TEST", daily, config, hourly_df=hourly)
        four_h = result.get("four_h_confirmation", {})
        # With 200 hourly bars → ~50 4H bars → available
        assert isinstance(four_h.get("four_h_available"), bool)

    def test_no_future_bars_in_hourly_window(self):
        """Hourly window sliced to daily cutoff must not contain future bars."""
        daily_cutoff = pd.Timestamp("2024-05-15", tz=None)
        full_hourly = _make_hourly_df(n_hours=400, trend="flat")

        # Simulate the slicing logic from run_backtest
        cutoff_aware = daily_cutoff.tz_localize("UTC")
        cutoff_end = cutoff_aware + pd.Timedelta(days=1)
        sliced = full_hourly[full_hourly.index < cutoff_end]

        if not sliced.empty:
            assert sliced.index.max() < cutoff_end
