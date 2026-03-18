"""Integration tests for GET /synthesize/{ticker}.

Verifies SSE event-stream format, 404 on unknown ticker, and 503 when
the AI API key is not configured.
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_price_data(sample_price_list):
    """Return mock (ticker_info, price_list, source) tuple for synthesis tests."""
    ticker_info = {
        "symbol": "TEST",
        "company_name": "Test Corp",
        "sector": "Technology",
        "market_cap": 1_000_000_000,
    }
    return ticker_info, sample_price_list, "cache"


async def _async_gen(*chunks):
    for chunk in chunks:
        yield chunk


class TestSynthesizeEndpoint:
    @patch("app.routers.synthesis.ANTHROPIC_API_KEY", "test-key")
    @patch("app.routers.synthesis.stream_narrative")
    @patch("app.routers.synthesis.get_or_refresh_data")
    def test_streams_sse_format(self, mock_get, mock_stream, authed_client, mock_price_data):
        mock_get.return_value = mock_price_data
        mock_stream.return_value = _async_gen("Hello", " world", "[DONE]")

        response = authed_client.get("/synthesize/TEST")

        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.text
        assert "data: Hello\n\n" in body
        assert "data: [DONE]\n\n" in body

    @patch("app.routers.synthesis.get_or_refresh_data")
    def test_404_on_invalid_ticker(self, mock_get, authed_client):
        mock_get.side_effect = ValueError("No data found for INVALID")
        response = authed_client.get("/synthesize/INVALID")
        assert response.status_code == 404

    @patch("app.routers.synthesis.stream_narrative")
    @patch("app.routers.synthesis.get_or_refresh_data")
    def test_503_on_missing_api_key(self, mock_get, mock_stream, authed_client, mock_price_data):
        mock_get.return_value = mock_price_data
        mock_stream.side_effect = RuntimeError("ANTHROPIC_API_KEY is not set.")

        response = authed_client.get("/synthesize/TEST")

        assert response.status_code == 503
