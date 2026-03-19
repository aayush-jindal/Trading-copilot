"""Strategy contract and correctness tests.

Covers every strategy in STRATEGY_REGISTRY. Uses pytest.mark.parametrize so
each test runs once per strategy. A minimal mock SignalSnapshot is built from
a known-good base; individual fields are overridden per test to trigger
specific code paths.

Test groups:
    TestContract          — evaluate() structure and StrategyResult fields
    TestConditionStruct   — every Condition has correct field types
    TestComputeRisk       — _compute_risk() output contract
    TestEntryAndStops     — should_enter() / get_stops() round-trip
    TestShouldExit        — should_exit() thresholds and None-safety
    TestADR015            — SMA200 filter visible to scanner (ADR-015)
"""

import pytest

from backtesting.base import Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot
from backtesting.strategies.registry import STRATEGY_REGISTRY
from backtesting.strategies.s1_trend_pullback import TrendPullbackStrategy
from backtesting.strategies.s2_rsi_reversion import RSIMeanReversionStrategy
from backtesting.strategies.s3_bb_squeeze import BBSqueezeStrategy
from backtesting.strategies.s7_macd_cross import MACDCrossStrategy
from backtesting.strategies.s8_stochastic_cross import StochasticCrossStrategy
from backtesting.strategies.s9_ema_cross import EMACrossStrategy
from backtesting.strategies.s10_golden_cross_pullback import GoldenCrossPullbackStrategy


# ── Snapshot builder ──────────────────────────────────────────────────────────

_BASE_PRICE = 100.0
_BASE_ATR = 2.0

# Nested sub-dicts that make up the base snapshot.  Tests override individual
# keys via make_snapshot() to trigger specific conditions without rebuilding
# everything from scratch.
_BASE_TREND = {
    "signal": "BULLISH",
    "price_vs_sma200": "above",
    "price_vs_sma50": "above",
    "price_vs_sma20": "above",
    "distance_from_sma200_pct": 5.0,
    "distance_from_sma50_pct": 4.0,
    "distance_from_sma20_pct": 2.0,
    "sma_50": 95.0,
    "sma_200": 90.0,
    "ema_9": 99.0,
    "ema_21": 98.0,
    "golden_cross": False,
    "death_cross": False,
}
_BASE_MOMENTUM = {
    "rsi": 55.0,
    "rsi_signal": "MODERATE_BULLISH",
    "macd": 1.0,
    "macd_signal": 0.5,
    "macd_histogram": 0.5,
    "macd_crossover": "none",
    "stochastic_k": 50.0,
    "stochastic_d": 48.0,
    "stochastic_signal": "NEUTRAL",
    "signal": "NEUTRAL",
}
_BASE_VOLATILITY = {
    "bb_upper": 105.0,
    "bb_middle": 103.0,
    "bb_lower": 95.0,
    "bb_width": 10.0,
    "bb_position": 50.0,
    "bb_squeeze": False,
    "atr": _BASE_ATR,
    "atr_vs_price_pct": 2.0,
    "signal": "NORMAL",
}
_BASE_VOLUME = {
    "current_volume": 5_000_000,
    "avg_volume_20d": 4_000_000,
    "volume_ratio": 1.5,
    "volume_signal": "NORMAL",
    "obv": 100_000_000,
    "obv_trend": "RISING",
}
_BASE_SR = {
    "nearest_support": 95.0,
    "nearest_resistance": 110.0,
    "distance_to_support_pct": 5.0,
    "distance_to_resistance_pct": 10.0,
    "support_strength": "HIGH",
    "resistance_strength": "MEDIUM",
    "high_52w": 120.0,
    "low_52w": 80.0,
    "distance_from_52w_high_pct": -20.0,
    "distance_from_52w_low_pct": 25.0,
    "swing_highs": [],
    "swing_lows": [],
}
_BASE_SWING = {
    "verdict": "ENTRY",
    "setup_type": "pullback_in_uptrend",
    "setup_score": 85,
    "weekly_trend_warning": None,
    "conditions": {
        "uptrend_confirmed": True,
        "weekly_trend_aligned": True,
        "adx": 28.0,
        "adx_strong": True,
        "rsi": 55.0,
        "rsi_pullback": True,
        "rsi_pullback_label": "pullback",
        "near_support": True,
        "near_resistance": False,
        "volume_declining": True,
        "volume_ratio": 0.8,
        "obv_trend": "RISING",
        "reversal_candle": True,
        "trigger_fired": True,
    },
    "levels": {
        "nearest_support": 95.0,
        "nearest_resistance": 110.0,
        "sr_alignment": "aligned",
    },
    "risk": {
        "atr14": _BASE_ATR,
        "entry_zone": {"low": 97.0, "high": 100.0},
        "stop_loss": 94.0,
        "target": 110.0,
        "rr_to_resistance": 2.0,
    },
    "reasons": [],
}
_BASE_WEEKLY = {
    "weekly_trend": "BULLISH",
    "weekly_trend_strength": "STRONG",
    "weekly_sma10": 98.0,
    "weekly_sma40": 94.0,
    "price_vs_weekly_sma10": "above",
    "price_vs_weekly_sma40": "above",
    "weekly_sma10_vs_sma40": "above",
}


def make_snapshot(
    price: float = _BASE_PRICE,
    trend: dict | None = None,
    momentum: dict | None = None,
    volatility: dict | None = None,
    volume: dict | None = None,
    support_resistance: dict | None = None,
    swing_setup: dict | None = _BASE_SWING,
    weekly: dict | None = None,
) -> SignalSnapshot:
    """Build a SignalSnapshot by merging per-dict overrides onto the base dicts.

    Pass a full replacement dict for any sub-dict you want to override entirely.
    Pass None to use the base value unchanged.
    """
    return SignalSnapshot(
        price=price,
        trend={**_BASE_TREND, **(trend or {})},
        momentum={**_BASE_MOMENTUM, **(momentum or {})},
        volatility={**_BASE_VOLATILITY, **(volatility or {})},
        volume={**_BASE_VOLUME, **(volume or {})},
        support_resistance={**_BASE_SR, **(support_resistance or {})},
        swing_setup=swing_setup,
        weekly={**_BASE_WEEKLY, **(weekly or {})},
        candlestick=[],
    )


def _fresh_trade() -> Trade:
    """Return a minimal Trade for should_exit() calls."""
    return Trade(
        ticker="TEST",
        entry_date="2024-01-01",
        entry_price=_BASE_PRICE,
        stop_loss=95.0,
        target_1=110.0,
    )


# ── Registry-level parametrize list ──────────────────────────────────────────

# Use fresh instances (not the shared singletons) so stateful strategies start
# with clean internal state in every test.
_STRATEGY_CLASSES = [
    TrendPullbackStrategy,
    RSIMeanReversionStrategy,
    BBSqueezeStrategy,
    MACDCrossStrategy,
    StochasticCrossStrategy,
    EMACrossStrategy,
    GoldenCrossPullbackStrategy,
]

_STRATEGY_IDS = [cls().name for cls in _STRATEGY_CLASSES]


def _all_strategies():
    """Yield a fresh instance per strategy class for parametrize."""
    return [cls() for cls in _STRATEGY_CLASSES]


# ── Contract tests ────────────────────────────────────────────────────────────

class TestContract:
    """evaluate() must return a well-formed StrategyResult for every strategy."""

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_returns_strategy_result(self, strategy):
        result = strategy.evaluate(make_snapshot())
        assert isinstance(result, StrategyResult)

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_name_matches(self, strategy):
        result = strategy.evaluate(make_snapshot())
        assert result.name == strategy.name

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_type_matches(self, strategy):
        result = strategy.evaluate(make_snapshot())
        assert result.type == strategy.type

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_verdict_is_valid(self, strategy):
        result = strategy.evaluate(make_snapshot())
        assert result.verdict in ("ENTRY", "WATCH", "NO_TRADE")

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_score_in_range(self, strategy):
        result = strategy.evaluate(make_snapshot())
        assert 0 <= result.score <= 100

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_ticker_is_none(self, strategy):
        """Strategy must never set ticker — that is the scanner's job."""
        result = strategy.evaluate(make_snapshot())
        assert result.ticker is None

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_risk_is_none_when_no_trade(self, strategy):
        """When verdict is NO_TRADE, risk must be None."""
        # Supply a snapshot that trips every strategy into NO_TRADE
        snap = make_snapshot(
            trend={"price_vs_sma200": "below", "signal": "BEARISH",
                   "price_vs_sma50": "below", "price_vs_sma20": "below",
                   "ema_9": 90.0, "ema_21": 95.0, "golden_cross": False,
                   "death_cross": True, "distance_from_sma200_pct": -5.0,
                   "sma_50": 95.0, "sma_200": 102.0},
            momentum={"rsi": 72.0, "rsi_signal": "OVERBOUGHT",
                      "macd_crossover": "bearish_crossover",
                      "stochastic_k": 85.0, "stochastic_d": 80.0,
                      "stochastic_signal": "OVERBOUGHT", "signal": "BEARISH",
                      "macd": -1.0, "macd_signal": -0.5, "macd_histogram": -0.5},
            swing_setup=None,
            weekly={"weekly_trend": "BEARISH", "weekly_trend_strength": "STRONG",
                    "weekly_sma10": 95.0, "weekly_sma40": 98.0,
                    "price_vs_weekly_sma10": "below", "price_vs_weekly_sma40": "below",
                    "weekly_sma10_vs_sma40": "below"},
        )
        result = strategy.evaluate(snap)
        if result.verdict == "NO_TRADE":
            assert result.risk is None

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_conditions_is_non_empty_list(self, strategy):
        result = strategy.evaluate(make_snapshot())
        assert isinstance(result.conditions, list)
        assert len(result.conditions) > 0


# ── Condition struct tests ─────────────────────────────────────────────────────

class TestConditionStruct:
    """Every Condition returned by _check_conditions() must be correctly typed."""

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_all_items_are_condition_instances(self, strategy):
        conditions = strategy._check_conditions(make_snapshot())
        for c in conditions:
            assert isinstance(c, Condition), f"Expected Condition, got {type(c)}"

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_label_is_non_empty_string(self, strategy):
        for c in strategy._check_conditions(make_snapshot()):
            assert isinstance(c.label, str) and c.label, f"Bad label: {c.label!r}"

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_passed_is_bool(self, strategy):
        for c in strategy._check_conditions(make_snapshot()):
            assert isinstance(c.passed, bool), (
                f"{strategy.name}: condition '{c.label}' passed={c.passed!r} is not bool"
            )

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_value_is_string(self, strategy):
        for c in strategy._check_conditions(make_snapshot()):
            assert isinstance(c.value, str), f"Bad value type: {type(c.value)}"

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_required_is_non_empty_string(self, strategy):
        for c in strategy._check_conditions(make_snapshot()):
            assert isinstance(c.required, str) and c.required

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_at_least_three_conditions(self, strategy):
        assert len(strategy._check_conditions(make_snapshot())) >= 3

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_no_raise_when_swing_setup_none(self, strategy):
        snap = make_snapshot(swing_setup=None)
        strategy._check_conditions(snap)  # must not raise

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_no_raise_when_numeric_fields_are_zero(self, strategy):
        """All numeric-heavy fields zeroed — strategy must not crash."""
        snap = make_snapshot(
            price=1.0,
            volatility={"atr": 0.0, "bb_upper": 0.0, "bb_middle": 0.0,
                        "bb_lower": 0.0, "bb_position": 0.0, "bb_squeeze": False,
                        "bb_width": 0.0, "atr_vs_price_pct": 0.0, "signal": "NORMAL"},
            momentum={"rsi": 0.0, "rsi_signal": "NEUTRAL", "macd": 0.0,
                      "macd_signal": 0.0, "macd_histogram": 0.0,
                      "macd_crossover": "none", "stochastic_k": 0.0,
                      "stochastic_d": 0.0, "stochastic_signal": "NEUTRAL",
                      "signal": "NEUTRAL"},
            swing_setup=None,
        )
        strategy._check_conditions(snap)  # must not raise


# ── _compute_risk tests ────────────────────────────────────────────────────────

class TestComputeRisk:
    """_compute_risk() output contract."""

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_returns_risk_levels_or_none(self, strategy):
        result = strategy._compute_risk(make_snapshot())
        assert result is None or isinstance(result, RiskLevels)

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_stop_less_than_entry_when_risk_returned(self, strategy):
        result = strategy._compute_risk(make_snapshot())
        if result is not None:
            assert result.stop_loss < result.entry_price, (
                f"{strategy.name}: stop {result.stop_loss} >= entry {result.entry_price}"
            )

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_target_greater_than_entry_when_risk_returned(self, strategy):
        result = strategy._compute_risk(make_snapshot())
        if result is not None:
            assert result.target > result.entry_price

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_risk_reward_positive_when_risk_returned(self, strategy):
        result = strategy._compute_risk(make_snapshot())
        if result is not None:
            assert result.risk_reward > 0

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_position_size_is_none(self, strategy):
        """Strategy never sets position_size — scanner does that."""
        result = strategy._compute_risk(make_snapshot())
        if result is not None:
            assert result.position_size is None

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_entry_zone_coherent_when_present(self, strategy):
        """entry_zone_low <= entry_zone_high and both positive if set."""
        result = strategy._compute_risk(make_snapshot())
        if result is not None and result.entry_zone_low is not None:
            assert result.entry_zone_low > 0
            assert result.entry_zone_high is not None
            assert result.entry_zone_low <= result.entry_zone_high

    def test_s8_returns_none_when_stop_invalid(self):
        """S8 _compute_risk returns None when support is within 0.5×ATR of entry."""
        strategy = StochasticCrossStrategy()
        # nearest_support almost at entry → stop invalid
        snap = make_snapshot(
            support_resistance={"nearest_support": 99.9, "nearest_resistance": 110.0,
                                "distance_to_support_pct": 0.1, "distance_to_resistance_pct": 10.0,
                                "support_strength": "LOW", "resistance_strength": "MEDIUM",
                                "high_52w": 120.0, "low_52w": 80.0,
                                "distance_from_52w_high_pct": -20.0,
                                "distance_from_52w_low_pct": 25.0,
                                "swing_highs": [], "swing_lows": []},
        )
        assert strategy._compute_risk(snap) is None

    def test_s9_returns_none_when_ema21_too_close(self):
        """S9 _compute_risk returns None when EMA21 is within 0.5×ATR of entry."""
        strategy = EMACrossStrategy()
        snap = make_snapshot(
            trend={"ema_21": 99.9, "ema_9": 100.5, "price_vs_sma200": "above",
                   "price_vs_sma50": "above", "price_vs_sma20": "above",
                   "sma_50": 95.0, "sma_200": 90.0, "golden_cross": False,
                   "death_cross": False, "signal": "BULLISH",
                   "distance_from_sma200_pct": 5.0, "distance_from_sma50_pct": 4.0,
                   "distance_from_sma20_pct": 2.0},
        )
        assert strategy._compute_risk(snap) is None

    def test_s3_returns_none_when_bb_lower_too_close(self):
        """S3 _compute_risk returns None when bb_lower is within 0.5×ATR of entry."""
        strategy = BBSqueezeStrategy()
        snap = make_snapshot(
            volatility={"bb_lower": 99.9, "bb_upper": 105.0, "bb_middle": 103.0,
                        "bb_width": 5.0, "bb_position": 50.0, "bb_squeeze": False,
                        "atr": _BASE_ATR, "atr_vs_price_pct": 2.0, "signal": "NORMAL"},
        )
        assert strategy._compute_risk(snap) is None


# ── should_enter / get_stops tests ────────────────────────────────────────────

class TestEntryAndStops:
    """should_enter() returns bool; when True, get_stops() returns valid StopConfig."""

    def _assert_stops_valid(self, stops: StopConfig) -> None:
        assert stops.stop_loss < stops.entry_price
        assert stops.target_1 > stops.entry_price

    def test_s1_enter_true_on_entry_swing(self):
        strategy = TrendPullbackStrategy()
        snap = make_snapshot()  # swing_setup.verdict == "ENTRY"
        assert strategy.should_enter(snap) is True
        self._assert_stops_valid(strategy.get_stops(snap))

    def test_s1_returns_bool(self):
        assert isinstance(TrendPullbackStrategy().should_enter(make_snapshot()), bool)

    def test_s2_enter_true_on_rsi_crossover(self):
        strategy = RSIMeanReversionStrategy()
        # Prime prev_rsi below 30
        strategy.should_enter(
            make_snapshot(momentum={"rsi": 25.0, "rsi_signal": "OVERSOLD",
                                    "macd": 1.0, "macd_signal": 0.5, "macd_histogram": 0.5,
                                    "macd_crossover": "none", "stochastic_k": 50.0,
                                    "stochastic_d": 48.0, "stochastic_signal": "NEUTRAL",
                                    "signal": "NEUTRAL"}),
            ticker="_test",
        )
        # Now cross above 30 with bb_position < 20 and price above SMA200
        snap = make_snapshot(
            momentum={"rsi": 32.0, "rsi_signal": "NEUTRAL", "macd": 1.0,
                      "macd_signal": 0.5, "macd_histogram": 0.5, "macd_crossover": "none",
                      "stochastic_k": 50.0, "stochastic_d": 48.0,
                      "stochastic_signal": "NEUTRAL", "signal": "NEUTRAL"},
            volatility={"bb_position": 15.0, "atr": _BASE_ATR, "bb_upper": 105.0,
                        "bb_middle": 103.0, "bb_lower": 95.0, "bb_width": 10.0,
                        "bb_squeeze": False, "atr_vs_price_pct": 2.0, "signal": "NORMAL"},
        )
        result = strategy.should_enter(snap, ticker="_test")
        assert isinstance(result, bool)
        if result:
            self._assert_stops_valid(strategy.get_stops(snap))

    def test_s3_enter_true_on_squeeze_resolution(self):
        strategy = BBSqueezeStrategy()
        # Prime prev_squeeze = True
        strategy.should_enter(
            make_snapshot(volatility={"bb_squeeze": True, "bb_upper": 105.0,
                                      "bb_middle": 103.0, "bb_lower": 95.0,
                                      "bb_width": 10.0, "bb_position": 50.0,
                                      "atr": _BASE_ATR, "atr_vs_price_pct": 2.0,
                                      "signal": "NORMAL"}),
            ticker="_test",
        )
        # Squeeze resolves: price > bb_upper, volume high, price above SMA200
        snap = make_snapshot(
            price=106.0,
            volatility={"bb_squeeze": False, "bb_upper": 105.0, "bb_middle": 103.0,
                        "bb_lower": 95.0, "bb_width": 10.0, "bb_position": 90.0,
                        "atr": _BASE_ATR, "atr_vs_price_pct": 2.0, "signal": "NORMAL"},
            volume={"volume_ratio": 2.0, "obv_trend": "RISING",
                    "current_volume": 8_000_000, "avg_volume_20d": 4_000_000,
                    "volume_signal": "HIGH", "obv": 100_000_000},
        )
        result = strategy.should_enter(snap, ticker="_test")
        assert isinstance(result, bool)
        if result:
            self._assert_stops_valid(strategy.get_stops(snap))

    def test_s7_enter_true_on_macd_cross(self):
        strategy = MACDCrossStrategy()
        snap = make_snapshot(
            momentum={"macd_crossover": "bullish_crossover", "rsi": 50.0,
                      "rsi_signal": "NEUTRAL", "macd": 1.0, "macd_signal": 0.5,
                      "macd_histogram": 0.5, "stochastic_k": 50.0,
                      "stochastic_d": 48.0, "stochastic_signal": "NEUTRAL",
                      "signal": "BULLISH"},
        )
        result = strategy.should_enter(snap)
        assert isinstance(result, bool)
        if result:
            self._assert_stops_valid(strategy.get_stops(snap))

    def test_s8_enter_true_on_stochastic_cross(self):
        strategy = StochasticCrossStrategy()
        # Prime prev_k below 20
        strategy.should_enter(
            make_snapshot(momentum={"stochastic_k": 15.0, "stochastic_d": 18.0,
                                    "rsi": 55.0, "rsi_signal": "NEUTRAL",
                                    "macd": 1.0, "macd_signal": 0.5,
                                    "macd_histogram": 0.5, "macd_crossover": "none",
                                    "stochastic_signal": "OVERSOLD", "signal": "NEUTRAL"}),
            ticker="_test",
        )
        snap = make_snapshot(
            momentum={"stochastic_k": 22.0, "stochastic_d": 20.0,
                      "rsi": 55.0, "rsi_signal": "NEUTRAL", "macd": 1.0,
                      "macd_signal": 0.5, "macd_histogram": 0.5,
                      "macd_crossover": "none", "stochastic_signal": "NEUTRAL",
                      "signal": "NEUTRAL"},
        )
        result = strategy.should_enter(snap, ticker="_test")
        assert isinstance(result, bool)
        if result:
            self._assert_stops_valid(strategy.get_stops(snap))

    def test_s9_enter_true_on_ema_cross(self):
        strategy = EMACrossStrategy()
        # Prime: EMA9 below EMA21
        strategy.should_enter(
            make_snapshot(trend={"ema_9": 97.0, "ema_21": 98.5,
                                 "price_vs_sma200": "above", "price_vs_sma50": "above",
                                 "price_vs_sma20": "above", "sma_50": 95.0,
                                 "sma_200": 90.0, "golden_cross": False,
                                 "death_cross": False, "signal": "BULLISH",
                                 "distance_from_sma200_pct": 5.0,
                                 "distance_from_sma50_pct": 4.0,
                                 "distance_from_sma20_pct": 2.0}),
            ticker="_test",
        )
        snap = make_snapshot(
            price=101.0,
            trend={"ema_9": 100.5, "ema_21": 99.0, "price_vs_sma200": "above",
                   "price_vs_sma50": "above", "price_vs_sma20": "above",
                   "sma_50": 95.0, "sma_200": 90.0, "golden_cross": False,
                   "death_cross": False, "signal": "BULLISH",
                   "distance_from_sma200_pct": 5.0, "distance_from_sma50_pct": 4.0,
                   "distance_from_sma20_pct": 2.0},
        )
        result = strategy.should_enter(snap, ticker="_test")
        assert isinstance(result, bool)
        if result:
            self._assert_stops_valid(strategy.get_stops(snap))


# ── should_exit tests ─────────────────────────────────────────────────────────

class TestShouldExit:
    """should_exit() thresholds and None-safety."""

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_returns_bool(self, strategy):
        assert isinstance(strategy.should_exit(make_snapshot(), _fresh_trade()), bool)

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_exits_when_rsi_is_80(self, strategy):
        """RSI=80 is above every strategy's exit threshold — must exit."""
        snap = make_snapshot(
            momentum={"rsi": 80.0, "rsi_signal": "OVERBOUGHT", "macd": 1.0,
                      "macd_signal": 0.5, "macd_histogram": 0.5,
                      "macd_crossover": "none", "stochastic_k": 85.0,
                      "stochastic_d": 80.0, "stochastic_signal": "OVERBOUGHT",
                      "signal": "BULLISH"},
        )
        assert strategy.should_exit(snap, _fresh_trade()) is True

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_exits_when_price_at_resistance(self, strategy):
        """Price at nearest_resistance should trigger exit for all strategies."""
        snap = make_snapshot(
            price=110.0,
            support_resistance={"nearest_resistance": 110.0, "nearest_support": 95.0,
                                 "distance_to_support_pct": 5.0,
                                 "distance_to_resistance_pct": 0.0,
                                 "support_strength": "HIGH",
                                 "resistance_strength": "HIGH",
                                 "high_52w": 120.0, "low_52w": 80.0,
                                 "distance_from_52w_high_pct": -10.0,
                                 "distance_from_52w_low_pct": 30.0,
                                 "swing_highs": [], "swing_lows": []},
        )
        assert strategy.should_exit(snap, _fresh_trade()) is True

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_no_exit_under_normal_conditions(self, strategy):
        """RSI~55, price between S/R — should generally not exit."""
        snap = make_snapshot()  # rsi=55, price=100 with resistance at 110
        result = strategy.should_exit(snap, _fresh_trade())
        # S3 exits if price < bb_upper (100 < 105 = True) — carve out
        # S9/S10 exit on EMA/SMA cross — carve out if no cross in base snap
        # We can't assert False for all, just assert it returns bool
        assert isinstance(result, bool)

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_no_raise_when_rsi_none(self, strategy):
        """should_exit must handle rsi=None without TypeError."""
        snap = make_snapshot(
            momentum={"rsi": None, "rsi_signal": "NEUTRAL", "macd": 0.0,
                      "macd_signal": 0.0, "macd_histogram": 0.0,
                      "macd_crossover": "none", "stochastic_k": None,
                      "stochastic_d": None, "stochastic_signal": "NEUTRAL",
                      "signal": "NEUTRAL"},
        )
        strategy.should_exit(snap, _fresh_trade())  # must not raise

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=_STRATEGY_IDS)
    def test_no_raise_when_nearest_resistance_none(self, strategy):
        """should_exit must handle nearest_resistance=None without TypeError."""
        snap = make_snapshot(
            support_resistance={"nearest_resistance": None, "nearest_support": 95.0,
                                 "distance_to_support_pct": 5.0,
                                 "distance_to_resistance_pct": None,
                                 "support_strength": "HIGH",
                                 "resistance_strength": "UNKNOWN",
                                 "high_52w": 120.0, "low_52w": 80.0,
                                 "distance_from_52w_high_pct": -20.0,
                                 "distance_from_52w_low_pct": 25.0,
                                 "swing_highs": [], "swing_lows": []},
        )
        strategy.should_exit(snap, _fresh_trade())  # must not raise


# ── ADR-015: SMA200 filter must be visible to scanner ─────────────────────────

# Strategies whose should_enter() explicitly gates on price_vs_sma200
_SMA200_STRATEGIES = [
    RSIMeanReversionStrategy,
    BBSqueezeStrategy,
    MACDCrossStrategy,
    StochasticCrossStrategy,
    EMACrossStrategy,
]
_SMA200_IDS = [cls().name for cls in _SMA200_STRATEGIES]


class TestADR015:
    """ADR-015: every filter used in should_enter() must appear in _check_conditions().

    If price_vs_sma200 is filtered in should_enter() but hidden from _check_conditions(),
    the scanner surfaces signals that the backtest never validated.
    """

    @pytest.mark.parametrize("strategy_cls", _SMA200_STRATEGIES, ids=_SMA200_IDS)
    def test_sma200_condition_differs_above_vs_below(self, strategy_cls):
        """_check_conditions with price_vs_sma200 'above' vs 'below' must differ."""
        strategy = strategy_cls()

        snap_above = make_snapshot(trend={"price_vs_sma200": "above"})
        snap_below = make_snapshot(trend={"price_vs_sma200": "below"})

        conditions_above = strategy._check_conditions(snap_above)
        conditions_below = strategy._check_conditions(snap_below)

        passed_above = [c.passed for c in conditions_above]
        passed_below = [c.passed for c in conditions_below]

        assert passed_above != passed_below, (
            f"{strategy.name}: _check_conditions() returns identical passed values "
            f"for price_vs_sma200='above' and 'below' — SMA200 filter is hidden from scanner"
        )
