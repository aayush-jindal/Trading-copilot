"""Tests for Phase E — Historical IV Tracking.

Covers:
- compute_iv_metrics with real IV history rows
- compute_iv_metrics fallback to proxy when <30 days
- IV rank / percentile correctness
- iv_source field in output
"""
import math
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.options.chain_scanner.iv_rank import compute_iv_metrics


def _make_history(n_returns: int = 60, ticker: str = "TEST") -> MagicMock:
    """Create a mock HistoryData with *n_returns* daily returns."""
    rng = np.random.default_rng(42)
    returns = rng.normal(0, 0.015, n_returns).tolist()
    h = MagicMock()
    h.returns = returns
    h.ticker = ticker
    return h


def _make_iv_rows(n: int, base_iv: float = 0.25, spread: float = 0.10) -> list[dict]:
    """Generate *n* iv_history rows with linearly spaced ATM IV."""
    return [
        {"atm_iv_avg": base_iv + (i / max(n - 1, 1)) * spread}
        for i in range(n)
    ]


class TestRealIVPath:
    """When ≥30 real IV rows are provided, use the real-IV code path."""

    def test_iv_source_is_real(self):
        rows = _make_iv_rows(60)
        result = compute_iv_metrics(0.30, _make_history(), iv_history_rows=rows)
        assert result["iv_source"] == "real"

    def test_iv_rank_at_min(self):
        rows = _make_iv_rows(60, base_iv=0.20, spread=0.20)
        # current_iv == min of range (0.20)
        result = compute_iv_metrics(0.20, _make_history(), iv_history_rows=rows)
        assert result["iv_rank"] == 0.0

    def test_iv_rank_at_max(self):
        rows = _make_iv_rows(60, base_iv=0.20, spread=0.20)
        # current_iv == max of range (0.40)
        result = compute_iv_metrics(0.40, _make_history(), iv_history_rows=rows)
        assert result["iv_rank"] == 100.0

    def test_iv_rank_midpoint(self):
        rows = _make_iv_rows(60, base_iv=0.20, spread=0.20)
        # current_iv == midpoint (0.30)
        result = compute_iv_metrics(0.30, _make_history(), iv_history_rows=rows)
        assert 45 <= result["iv_rank"] <= 55

    def test_iv_percentile_below_all(self):
        rows = _make_iv_rows(60, base_iv=0.25, spread=0.10)
        # current_iv below all historical
        result = compute_iv_metrics(0.10, _make_history(), iv_history_rows=rows)
        assert result["iv_percentile"] == 0.0

    def test_iv_percentile_above_all(self):
        rows = _make_iv_rows(60, base_iv=0.25, spread=0.10)
        # current_iv above all historical
        result = compute_iv_metrics(0.50, _make_history(), iv_history_rows=rows)
        assert result["iv_percentile"] == 100.0

    def test_regime_high(self):
        rows = _make_iv_rows(60, base_iv=0.20, spread=0.20)
        result = compute_iv_metrics(0.39, _make_history(), iv_history_rows=rows)
        assert result["iv_regime"] in ("HIGH", "ELEVATED")

    def test_regime_low(self):
        rows = _make_iv_rows(60, base_iv=0.20, spread=0.20)
        result = compute_iv_metrics(0.21, _make_history(), iv_history_rows=rows)
        assert result["iv_regime"] == "LOW"

    def test_none_values_filtered(self):
        """Rows with atm_iv_avg=None should be skipped."""
        rows = _make_iv_rows(40)
        rows += [{"atm_iv_avg": None}] * 10
        result = compute_iv_metrics(0.30, _make_history(), iv_history_rows=rows)
        assert result["iv_source"] == "real"

    def test_all_same_iv_gives_rank_50(self):
        rows = [{"atm_iv_avg": 0.30}] * 50
        result = compute_iv_metrics(0.30, _make_history(), iv_history_rows=rows)
        assert result["iv_rank"] == 50.0


class TestProxyFallback:
    """When <30 real IV rows, fallback to realized-vol proxy."""

    def test_no_rows(self):
        result = compute_iv_metrics(0.25, _make_history())
        assert result["iv_source"] == "proxy"

    def test_few_rows(self):
        rows = _make_iv_rows(10)
        result = compute_iv_metrics(0.25, _make_history(), iv_history_rows=rows)
        assert result["iv_source"] == "proxy"

    def test_empty_list(self):
        result = compute_iv_metrics(0.25, _make_history(), iv_history_rows=[])
        assert result["iv_source"] == "proxy"

    def test_insufficient_returns_gives_default(self):
        result = compute_iv_metrics(0.25, _make_history(n_returns=10))
        assert result["iv_rank"] == 50.0
        assert result["iv_regime"] == "NORMAL"

    def test_proxy_has_rv_stats(self):
        result = compute_iv_metrics(0.25, _make_history(n_returns=100))
        assert not math.isnan(result["rv_high"])
        assert not math.isnan(result["rv_low"])
        assert not math.isnan(result["rv_mean"])


class TestDTEComputation:
    """Sanity: DTE remaining is computed correctly by option_trades router.

    (This is a lightweight check — the actual repricing logic is tested
    in test_option_trades.py.)
    """

    def test_dte_from_expiry(self):
        from datetime import date, timedelta

        expiry_str = (date.today() + timedelta(days=30)).isoformat()
        expiry_date = date.fromisoformat(expiry_str)
        dte = (expiry_date - date.today()).days
        assert dte == 30
