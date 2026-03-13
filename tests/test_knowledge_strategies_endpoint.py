"""Integration tests for GET /analyze/{ticker}/knowledge-strategies."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client_no_auth():
    """TestClient with no auth override — real JWT check applies."""
    return TestClient(app, raise_server_exceptions=False)


_MOCK_STRATEGIES = """\
## Applicable Strategies
**RSI Pullback Entry** — conditions MET
Entry: $213.45, Stop: $208.00, Target: $225.00

## Best Current Opportunity
Strong pullback-in-uptrend setup supported by Murphy p.247.

## Signals to Watch
- RSI holding above 40
- Volume confirming on any breakout
"""


class TestKnowledgeStrategiesEndpoint:
    def test_200_response_shape(self, authed_client):
        with patch("tools.knowledge_base.strategy_gen.generate_strategies", return_value=_MOCK_STRATEGIES):
            response = authed_client.get("/analyze/AAPL/knowledge-strategies")
        assert response.status_code == 200
        data = response.json()
        assert "ticker" in data
        assert "strategies" in data

    def test_ticker_uppercased_in_response(self, authed_client):
        with patch("tools.knowledge_base.strategy_gen.generate_strategies", return_value=_MOCK_STRATEGIES):
            response = authed_client.get("/analyze/aapl/knowledge-strategies")
        assert response.status_code == 200
        assert response.json()["ticker"] == "AAPL"

    def test_strategies_text_returned(self, authed_client):
        with patch("tools.knowledge_base.strategy_gen.generate_strategies", return_value=_MOCK_STRATEGIES):
            response = authed_client.get("/analyze/TSLA/knowledge-strategies")
        assert response.status_code == 200
        assert response.json()["strategies"] == _MOCK_STRATEGIES

    def test_500_on_exception(self, authed_client):
        with patch("tools.knowledge_base.strategy_gen.generate_strategies",
                   side_effect=RuntimeError("DB connection failed")):
            response = authed_client.get("/analyze/AAPL/knowledge-strategies")
        assert response.status_code == 500
        assert "RuntimeError" in response.json()["detail"]

    def test_500_detail_contains_error_message(self, authed_client):
        with patch("tools.knowledge_base.strategy_gen.generate_strategies",
                   side_effect=ValueError("knowledge base is empty")):
            response = authed_client.get("/analyze/AAPL/knowledge-strategies")
        assert response.status_code == 500
        assert "knowledge base is empty" in response.json()["detail"]

    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.get("/analyze/AAPL/knowledge-strategies")
        assert response.status_code == 401
