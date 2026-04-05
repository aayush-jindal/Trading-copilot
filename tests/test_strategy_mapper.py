"""
Unit tests for the strategy mapper (Phase B).

All inputs are synthetic OptionSignal instances — no network calls.
Covers every (iv_regime, direction) combination and edge cases.

Options Analytics Team — 2026-04
"""

import pytest

from app.services.options.chain_scanner import OptionSignal
from app.services.options.chain_scanner.strategy_mapper import (
    map_signal,
    StrategyRecommendation,
)


def _sig(**overrides) -> OptionSignal:
    """Build an OptionSignal with sensible defaults."""
    defaults = dict(
        ticker="AAPL", strike=250.0, expiry="2026-05-15", option_type="call",
        dte=35, spot=255.0, bid=5.0, ask=5.50, mid=5.25, open_interest=2000,
        bid_ask_spread_pct=9.5, chain_iv=0.30, iv_rank=50.0, iv_percentile=50.0,
        iv_regime="NORMAL", garch_vol=0.28, theo_price=5.30, edge_pct=5.0,
        direction="BUY", delta=0.40, gamma=0.02, theta=-0.05, vega=0.30,
        conviction=65.0,
    )
    defaults.update(overrides)
    return OptionSignal(**defaults)


# ======================================================================
# HIGH regime
# ======================================================================

class TestHighRegime:
    def test_high_sell_put(self):
        r = map_signal(_sig(iv_regime="HIGH", direction="SELL", option_type="put", delta=-0.35))
        assert r is not None
        assert r.strategy == "short_put_spread"
        assert r.risk_profile == "defined"
        assert r.edge_source == "iv_overpriced"
        assert len(r.legs) == 2

    def test_high_sell_call(self):
        r = map_signal(_sig(iv_regime="HIGH", direction="SELL", option_type="call", delta=0.35))
        assert r is not None
        assert r.strategy == "short_call_spread"
        assert len(r.legs) == 2

    def test_high_sell_low_delta_iron_condor(self):
        r = map_signal(_sig(iv_regime="HIGH", direction="SELL", option_type="call", delta=0.15))
        assert r is not None
        assert r.strategy == "iron_condor"
        assert len(r.legs) == 4

    def test_high_buy_returns_none(self):
        r = map_signal(_sig(iv_regime="HIGH", direction="BUY"))
        assert r is None


# ======================================================================
# ELEVATED regime
# ======================================================================

class TestElevatedRegime:
    def test_elevated_sell_put(self):
        r = map_signal(_sig(iv_regime="ELEVATED", direction="SELL", option_type="put", delta=-0.30))
        assert r is not None
        assert r.strategy == "short_put_spread"

    def test_elevated_sell_call(self):
        r = map_signal(_sig(iv_regime="ELEVATED", direction="SELL", option_type="call", delta=0.30))
        assert r is not None
        assert r.strategy == "short_call_spread"

    def test_elevated_buy_calendar(self):
        r = map_signal(_sig(iv_regime="ELEVATED", direction="BUY"))
        assert r is not None
        assert r.strategy == "calendar_spread"
        assert len(r.legs) == 2


# ======================================================================
# NORMAL regime
# ======================================================================

class TestNormalRegime:
    def test_normal_buy_call(self):
        r = map_signal(_sig(iv_regime="NORMAL", direction="BUY", option_type="call"))
        assert r is not None
        assert r.strategy == "long_call"
        assert r.edge_source == "directional"

    def test_normal_buy_put(self):
        r = map_signal(_sig(iv_regime="NORMAL", direction="BUY", option_type="put"))
        assert r is not None
        assert r.strategy == "long_put"

    def test_normal_sell_returns_none(self):
        r = map_signal(_sig(iv_regime="NORMAL", direction="SELL"))
        assert r is None


# ======================================================================
# LOW regime
# ======================================================================

class TestLowRegime:
    def test_low_buy_low_delta_straddle(self):
        r = map_signal(_sig(iv_regime="LOW", direction="BUY", delta=0.18))
        assert r is not None
        assert r.strategy == "long_straddle"
        assert r.edge_source == "iv_underpriced"

    def test_low_buy_call(self):
        r = map_signal(_sig(iv_regime="LOW", direction="BUY", option_type="call", delta=0.40))
        assert r is not None
        assert r.strategy == "long_call"

    def test_low_buy_put(self):
        r = map_signal(_sig(iv_regime="LOW", direction="BUY", option_type="put", delta=-0.40))
        assert r is not None
        assert r.strategy == "long_put"

    def test_low_sell_returns_none(self):
        r = map_signal(_sig(iv_regime="LOW", direction="SELL"))
        assert r is None


# ======================================================================
# Edge cases
# ======================================================================

class TestEdgeCases:
    def test_low_conviction_returns_none(self):
        r = map_signal(_sig(conviction=20.0))
        assert r is None

    def test_conviction_boundary_29_returns_none(self):
        r = map_signal(_sig(conviction=29.9))
        assert r is None

    def test_conviction_boundary_30_returns_recommendation(self):
        r = map_signal(_sig(conviction=30.0, iv_regime="NORMAL", direction="BUY"))
        assert r is not None

    def test_all_recommendations_have_rationale(self):
        """Every non-None result must have a non-empty rationale."""
        combos = [
            dict(iv_regime="HIGH", direction="SELL", option_type="put", delta=-0.35),
            dict(iv_regime="HIGH", direction="SELL", option_type="call", delta=0.35),
            dict(iv_regime="HIGH", direction="SELL", option_type="call", delta=0.15),
            dict(iv_regime="ELEVATED", direction="SELL", option_type="put", delta=-0.30),
            dict(iv_regime="ELEVATED", direction="BUY", option_type="call", delta=0.40),
            dict(iv_regime="NORMAL", direction="BUY", option_type="call", delta=0.40),
            dict(iv_regime="NORMAL", direction="BUY", option_type="put", delta=-0.40),
            dict(iv_regime="LOW", direction="BUY", option_type="call", delta=0.18),
            dict(iv_regime="LOW", direction="BUY", option_type="call", delta=0.40),
            dict(iv_regime="LOW", direction="BUY", option_type="put", delta=-0.40),
        ]
        for combo in combos:
            r = map_signal(_sig(**combo))
            assert r is not None, f"Expected recommendation for {combo}"
            assert r.rationale, f"Empty rationale for {combo}"
            assert len(r.rationale) > 10

    def test_all_recommendations_have_legs(self):
        """Every non-None result must have at least 1 leg."""
        combos = [
            dict(iv_regime="HIGH", direction="SELL", option_type="put", delta=-0.35),
            dict(iv_regime="NORMAL", direction="BUY", option_type="call", delta=0.40),
            dict(iv_regime="LOW", direction="BUY", option_type="call", delta=0.18),
        ]
        for combo in combos:
            r = map_signal(_sig(**combo))
            assert r is not None
            assert len(r.legs) >= 1

    def test_spreads_have_defined_risk(self):
        """All spread strategies should have risk_profile='defined'."""
        spread_combos = [
            dict(iv_regime="HIGH", direction="SELL", option_type="put", delta=-0.35),
            dict(iv_regime="HIGH", direction="SELL", option_type="call", delta=0.35),
            dict(iv_regime="HIGH", direction="SELL", option_type="call", delta=0.15),
            dict(iv_regime="ELEVATED", direction="SELL", option_type="put", delta=-0.30),
        ]
        for combo in spread_combos:
            r = map_signal(_sig(**combo))
            assert r is not None
            assert r.risk_profile == "defined"
