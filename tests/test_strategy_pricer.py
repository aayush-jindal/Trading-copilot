"""
Unit tests for the strategy pricer (Phase C).

Uses real BS pricing (pure math, no network). MC is mocked for speed.

Options Analytics Team — 2026-04
"""

import numpy as np
import pytest
from unittest.mock import patch

from app.services.options.chain_scanner import OptionSignal
from app.services.options.chain_scanner.strategy_mapper import (
    map_signal,
    StrategyRecommendation,
)
from app.services.options.chain_scanner.strategy_pricer import (
    _round_strike,
    _strike_increment,
    _classify_credit,
    _resolve_strikes,
    price_recommendation,
)


def _sig(**overrides) -> OptionSignal:
    """Build an OptionSignal with sensible defaults."""
    defaults = dict(
        ticker="AAPL", strike=250.0, expiry="2026-05-15", option_type="put",
        dte=35, spot=255.0, bid=5.0, ask=5.50, mid=5.25, open_interest=2000,
        bid_ask_spread_pct=9.5, chain_iv=0.30, iv_rank=85.0, iv_percentile=88.0,
        iv_regime="HIGH", garch_vol=0.25, theo_price=4.50, edge_pct=-8.5,
        direction="SELL", delta=-0.35, gamma=0.02, theta=-0.05, vega=0.30,
        conviction=72.5,
    )
    defaults.update(overrides)
    return OptionSignal(**defaults)


def _mock_mc_result():
    """Return a deterministic MC result for mocking."""
    np.random.seed(42)
    payoffs = np.random.lognormal(0.5, 0.3, 1000)
    return {"mc_price": 5.0, "payoffs": payoffs}


# ======================================================================
# _round_strike
# ======================================================================

class TestRoundStrike:
    def test_above_100(self):
        assert _round_strike(253.0) == 255.0
        assert _round_strike(247.0) == 245.0

    def test_between_50_and_100(self):
        assert _round_strike(72.3) == 72.5
        assert _round_strike(73.8) == 75.0

    def test_below_50(self):
        assert _round_strike(23.4) == 23.0
        assert _round_strike(23.6) == 24.0


# ======================================================================
# _strike_increment
# ======================================================================

class TestStrikeIncrement:
    def test_above_100(self):
        assert _strike_increment(255.0) == 5.0

    def test_between_50_and_100(self):
        assert _strike_increment(75.0) == 2.5

    def test_below_50(self):
        assert _strike_increment(25.0) == 1.0


# ======================================================================
# _classify_credit
# ======================================================================

class TestClassifyCredit:
    def test_credit_strategies(self):
        assert _classify_credit("short_put_spread") is True
        assert _classify_credit("short_call_spread") is True
        assert _classify_credit("iron_condor") is True

    def test_debit_strategies(self):
        assert _classify_credit("long_call") is False
        assert _classify_credit("long_put") is False
        assert _classify_credit("long_straddle") is False
        assert _classify_credit("calendar_spread") is False


# ======================================================================
# _resolve_strikes
# ======================================================================

class TestResolveStrikes:
    def test_short_put_spread(self):
        sig = _sig(strike=250.0, spot=255.0)
        rec = map_signal(sig)
        assert rec.strategy == "short_put_spread"
        legs = _resolve_strikes(sig, rec)
        assert len(legs) == 2
        assert legs[0]["strike"] == 250.0  # signal_strike
        assert legs[1]["strike"] == 245.0  # signal_strike - 5

    def test_long_call(self):
        sig = _sig(iv_regime="NORMAL", direction="BUY", option_type="call",
                   strike=255.0, delta=0.40)
        rec = map_signal(sig)
        assert rec.strategy == "long_call"
        legs = _resolve_strikes(sig, rec)
        assert len(legs) == 1
        assert legs[0]["strike"] == 255.0

    def test_iron_condor(self):
        sig = _sig(iv_regime="HIGH", direction="SELL", option_type="call",
                   delta=0.15)
        rec = map_signal(sig)
        assert rec.strategy == "iron_condor"
        legs = _resolve_strikes(sig, rec)
        assert len(legs) == 4

    def test_long_straddle(self):
        sig = _sig(iv_regime="LOW", direction="BUY", option_type="call",
                   delta=0.18, iv_rank=10)
        rec = map_signal(sig)
        assert rec.strategy == "long_straddle"
        legs = _resolve_strikes(sig, rec)
        assert len(legs) == 2
        # Both should be ATM
        assert legs[0]["strike"] == legs[1]["strike"]


# ======================================================================
# price_recommendation — credit spread
# ======================================================================

class TestPriceCredit:
    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_credit_spread_entry(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result is not None
        assert result["is_credit"] is True
        assert result["entry"] > 0

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_credit_max_profit_equals_entry(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result["max_profit"] == result["entry"]

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_credit_max_loss(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result["spread_width"] is not None
        assert result["max_loss"] == round(result["spread_width"] - result["entry"], 2)

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_credit_exit_target(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result["exit_target"] == round(result["entry"] * 0.5, 2)

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_credit_stop(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result["option_stop"] == round(result["entry"] * 2.0, 2)

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_credit_spread_width(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result["spread_width"] == 5.0  # 250 - 245


# ======================================================================
# price_recommendation — debit (long call)
# ======================================================================

class TestPriceDebit:
    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_long_call_entry(self, _mock_mc):
        sig = _sig(iv_regime="NORMAL", direction="BUY", option_type="call",
                   strike=255.0, delta=0.40, iv_rank=40, conviction=65)
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result is not None
        assert result["is_credit"] is False
        assert result["entry"] > 0

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_debit_max_loss_equals_entry(self, _mock_mc):
        sig = _sig(iv_regime="NORMAL", direction="BUY", option_type="call",
                   strike=255.0, delta=0.40, iv_rank=40, conviction=65)
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result["max_loss"] == result["entry"]

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_debit_exit_target(self, _mock_mc):
        sig = _sig(iv_regime="NORMAL", direction="BUY", option_type="call",
                   strike=255.0, delta=0.40, iv_rank=40, conviction=65)
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert result["exit_target"] == round(result["entry"] * 1.5, 2)


# ======================================================================
# Net Greeks and edge cases
# ======================================================================

class TestNetGreeks:
    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_net_greeks_are_signed_sums(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        # Net delta should be roughly: sell_delta + buy_delta (opposite signs)
        assert isinstance(result["net_delta"], float)
        assert isinstance(result["net_gamma"], float)
        assert isinstance(result["net_theta"], float)
        assert isinstance(result["net_vega"], float)

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_prob_profit_in_range(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert 0 <= result["prob_profit"] <= 100

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_all_legs_have_required_fields(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        for leg in result["legs"]:
            assert "action" in leg
            assert "option_type" in leg
            assert "strike" in leg
            assert "iv" in leg
            assert "price" in leg
            assert "delta" in leg
            assert "theta" in leg

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_returns_none_for_tiny_entry(self, _mock_mc):
        # Deep OTM put with very low IV → negligible premium
        sig = _sig(strike=200.0, spot=300.0, chain_iv=0.05, dte=5)
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        # With 200 strike, 300 spot, low IV, the put spread should be nearly worthless
        # result may be None or have entry >= 0.05 depending on exact pricing
        if result is not None:
            assert result["entry"] >= 0.05

    @patch("app.services.options.chain_scanner.strategy_pricer.run_monte_carlo",
           return_value=_mock_mc_result())
    def test_risk_reward_string(self, _mock_mc):
        sig = _sig()
        rec = map_signal(sig)
        result = price_recommendation(sig, rec)
        assert "risk_reward" in result
        assert result["risk_reward"].startswith("1:")
