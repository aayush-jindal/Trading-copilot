import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.main import app


@pytest.fixture
def authed_client():
    """TestClient with get_current_user dependency overridden (no real JWT needed)."""
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "username": "testuser"}
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_ohlcv_df():
    """Generate synthetic OHLCV DataFrame with controllable trend/volatility."""

    def _make(days=300, start_price=100.0, trend="flat", volatility=0.02):
        np.random.seed(42)
        # Roll back to the last business day so date_range always produces
        # exactly `days` entries regardless of the current weekday (pandas 3.x
        # returns N-1 entries when `end` is a non-business day).
        _end = pd.offsets.BDay().rollback(pd.Timestamp.today().normalize())
        dates = pd.date_range(end=_end, periods=days, freq="B")
        n = len(dates)

        # Random walk with trend bias
        drift = {"up": 0.001, "down": -0.001, "flat": 0.0}[trend]
        returns = np.random.normal(drift, volatility, n)
        close = start_price * np.cumprod(1 + returns)

        # Build OHLCV from close
        high = close * (1 + np.abs(np.random.normal(0, volatility / 2, n)))
        low = close * (1 - np.abs(np.random.normal(0, volatility / 2, n)))
        open_ = close * (1 + np.random.normal(0, volatility / 3, n))
        volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)

        df = pd.DataFrame({
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }, index=dates)
        df.index.name = "date"
        return df

    return _make


@pytest.fixture
def sample_df(mock_ohlcv_df):
    """Default 300-day uptrend DataFrame."""
    return mock_ohlcv_df(days=300, trend="up")


@pytest.fixture
def sample_price_list(sample_df):
    """Convert sample_df to list[dict] format matching DB output."""
    df = sample_df.reset_index()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df.to_dict("records")
