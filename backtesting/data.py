"""
DataProvider ABC and YFinanceProvider implementation.

Fetches OHLCV data directly via yfinance — does NOT call
get_or_refresh_data(), so no database connection is required.
"""

from abc import ABC, abstractmethod

import pandas as pd
import yfinance as yf

_REQUIRED_COLS = ["open", "high", "low", "close", "volume"]


class DataProvider(ABC):
    @abstractmethod
    def fetch_daily(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Return daily OHLCV DataFrame with DatetimeIndex, sorted ascending."""

    @abstractmethod
    def fetch_weekly(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Return weekly OHLCV DataFrame with DatetimeIndex, sorted ascending."""


class YFinanceProvider(DataProvider):
    def _download(self, ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
        df = yf.download(ticker, start=start, end=end, interval=interval,
                         auto_adjust=True, progress=False)
        if df.empty:
            raise ValueError(f"No data returned for {ticker}")

        # yfinance returns MultiIndex columns when downloading a single ticker
        # with some versions — flatten if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        # Keep only the columns we need (drop adj_close, dividends, etc.)
        present = [c for c in _REQUIRED_COLS if c in df.columns]
        df = df[present].copy()

        df = df.dropna(subset=["close"])
        df = df.sort_index()

        if len(df) < 100:
            raise ValueError(
                f"Insufficient data for {ticker}: got {len(df)} rows, need ≥ 100"
            )

        return df

    def fetch_daily(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return self._download(ticker, start, end, interval="1d")

    def fetch_weekly(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return self._download(ticker, start, end, interval="1wk")


DEFAULT_PROVIDER = YFinanceProvider()
