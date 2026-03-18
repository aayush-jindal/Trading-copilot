"""Integration tests for GET /analyze/{ticker}.

Verifies response structure, Pydantic model validation, swing_setup
field presence, 404 on invalid ticker, and individual signal sections.
"""

from unittest.mock import patch

import pytest

from app.models import AnalysisResponse


@pytest.fixture
def mock_price_data(sample_price_list):
    """Return mock data in the format get_or_refresh_data returns."""
    ticker_info = {
        "symbol": "TEST",
        "company_name": "Test Corp",
        "sector": "Technology",
        "market_cap": 1_000_000_000,
    }
    return ticker_info, sample_price_list, "cache"


class TestAnalyzeEndpoint:
    @patch("app.routers.analysis.get_or_refresh_data")
    def test_200_response(self, mock_get, authed_client, mock_price_data):
        mock_get.return_value = mock_price_data
        response = authed_client.get("/analyze/TEST")
        assert response.status_code == 200
        data = response.json()
        for key in ["ticker", "price", "trend", "momentum", "volatility", "volume", "support_resistance", "candlestick"]:
            assert key in data
        # swing_setup is optional — must be present (may be null)
        assert "swing_setup" in data

    @patch("app.routers.analysis.get_or_refresh_data")
    def test_response_validates_against_model(self, mock_get, authed_client, mock_price_data):
        mock_get.return_value = mock_price_data
        response = authed_client.get("/analyze/TEST")
        assert response.status_code == 200
        # Validates all fields including the new optional swing_setup
        AnalysisResponse(**response.json())

    @patch("app.routers.analysis.get_or_refresh_data")
    def test_swing_setup_field_present(self, mock_get, authed_client, mock_price_data):
        """swing_setup key must exist in response; value is dict or null."""
        mock_get.return_value = mock_price_data
        response = authed_client.get("/analyze/TEST")
        assert response.status_code == 200
        data = response.json()
        assert "swing_setup" in data
        swing = data["swing_setup"]
        if swing is not None:
            assert swing["setup_type"] == "pullback_in_uptrend"
            assert swing["verdict"] in ("ENTRY", "WATCH", "NO_TRADE")
            assert isinstance(swing["setup_score"], int)
            assert 0 <= swing["setup_score"] <= 100

    @patch("app.routers.analysis.get_or_refresh_data")
    def test_404_for_invalid_ticker(self, mock_get, authed_client):
        mock_get.side_effect = ValueError("No data found for INVALID")
        response = authed_client.get("/analyze/INVALID")
        assert response.status_code == 404

    @patch("app.routers.analysis.get_or_refresh_data")
    def test_trend_signals_present(self, mock_get, authed_client, mock_price_data):
        mock_get.return_value = mock_price_data
        response = authed_client.get("/analyze/TEST")
        trend = response.json()["trend"]
        assert "sma_20" in trend
        assert "signal" in trend
        assert trend["signal"] in ("BULLISH", "BEARISH", "NEUTRAL")

    @patch("app.routers.analysis.get_or_refresh_data")
    def test_momentum_signals_present(self, mock_get, authed_client, mock_price_data):
        mock_get.return_value = mock_price_data
        response = authed_client.get("/analyze/TEST")
        momentum = response.json()["momentum"]
        assert "rsi" in momentum
        assert "macd" in momentum
        assert "signal" in momentum
