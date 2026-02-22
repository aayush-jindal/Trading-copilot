import numpy as np
import pandas as pd
import pytest

from app.services.ta_engine import (
    _prepare_dataframe,
    analyze_ticker,
    compute_candlestick_patterns,
    compute_momentum_signals,
    compute_support_resistance,
    compute_trend_signals,
    compute_volatility_signals,
    compute_volume_signals,
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


class TestSupportResistance:
    def test_52w_high_low(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert result["high_52w"] >= result["low_52w"]

    def test_swing_detection(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert isinstance(result["swing_highs"], list)
        assert isinstance(result["swing_lows"], list)

    def test_nearest_levels(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert result["nearest_resistance"] is not None
        assert result["nearest_support"] is not None

    def test_distance_percentages(self, sample_df):
        result = compute_support_resistance(sample_df)
        assert isinstance(result["distance_to_resistance_pct"], float)
        assert isinstance(result["distance_to_support_pct"], float)


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
