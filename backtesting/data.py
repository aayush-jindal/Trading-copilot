"""
DataProvider ABC and YFinanceProvider implementation.

Fetches OHLCV data directly via yfinance — does NOT call
get_or_refresh_data(), so no database connection is required.

Data is cached locally in backtesting/ohlcv.db (SQLite).
Only the gap between what we have and what we need is fetched from yfinance.

Retry policy: up to 3 attempts with 2s back-off on transient failures.
Hard failure: raises ValueError if data is unavailable after all retries
AND not in the cache — callers must handle this explicitly.
"""

import time
from abc import ABC, abstractmethod
from datetime import date

import pandas as pd
import yfinance as yf

from backtesting.cache import _cache, DataCache

_REQUIRED_COLS = ["open", "high", "low", "close", "volume"]
_MAX_RETRIES   = 3
_RETRY_DELAY   = 2.0   # seconds between retries


class DataProvider(ABC):
    @abstractmethod
    def fetch_daily(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Return daily OHLCV DataFrame with DatetimeIndex, sorted ascending."""

    @abstractmethod
    def fetch_weekly(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Return weekly OHLCV DataFrame with DatetimeIndex, sorted ascending."""


class YFinanceProvider(DataProvider):
    def __init__(self, cache: DataCache = _cache):
        self._cache = cache

    def _download_raw(self, ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
        """
        Fetch from yfinance with retry on transient failures.

        Returns a normalised DataFrame (may be empty if the ticker has no data
        in the requested window — e.g. newly listed, or start == end).
        Raises DataFetchError after _MAX_RETRIES consecutive hard failures.
        """
        last_exc = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                df = yf.download(
                    ticker, start=start, end=end,
                    interval=interval, auto_adjust=True, progress=False,
                )
            except Exception as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
                continue

            if df is None or df.empty:
                return pd.DataFrame()   # no data in window — not a network error

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            present = [c for c in _REQUIRED_COLS if c in df.columns]
            if not present:
                return pd.DataFrame()
            df = df[present].copy()
            df = df.dropna(subset=["close"])
            df = df.sort_index()
            return df

        # All retries exhausted with exceptions
        raise DataFetchError(
            f"{ticker} ({interval} {start}→{end}): "
            f"download failed after {_MAX_RETRIES} attempts — {last_exc}"
        )

    def _fetch(self, ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
        """
        Return OHLCV for ticker in [start, end].

        1. Check cache coverage for (ticker, interval).
        2. Fetch only missing gap(s) from yfinance — with retry.
        3. Upsert new rows into cache.
        4. Return the requested range from cache.

        Raises ValueError if the final cache slice has < 100 rows
        (indicates the ticker has genuinely insufficient history).
        """
        today = str(date.today())
        effective_end = min(end, today)

        cov = self._cache.coverage(ticker, interval)

        if cov is None:
            df = self._download_raw(ticker, start, effective_end, interval)
            self._cache.upsert(ticker, df, interval)
        else:
            cached_min, cached_max = cov
            if start < cached_min:
                before = self._download_raw(ticker, start, cached_min, interval)
                self._cache.upsert(ticker, before, interval)
            if effective_end > cached_max:
                after = self._download_raw(ticker, cached_max, effective_end, interval)
                self._cache.upsert(ticker, after, interval)

        df = self._cache.load(ticker, start, effective_end, interval)
        if df.empty or len(df) < 100:
            raise ValueError(
                f"Insufficient data for {ticker} ({interval}): "
                f"got {len(df)} rows, need ≥ 100"
            )
        return df

    def fetch_daily(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return self._fetch(ticker, start, end, interval="1d")

    def fetch_weekly(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return self._fetch(ticker, start, end, interval="1wk")


class SQLiteProvider(DataProvider):
    """
    Read-only provider — loads OHLCV directly from the local SQLite cache.

    No network calls, no yfinance.  Raises ValueError if a ticker / window
    is not in the cache.  Use validate_cache.py to pre-populate the DB.
    """

    def __init__(self, cache: DataCache = _cache):
        self._cache = cache

    def _load(self, ticker: str, start: str, end: str, interval: str, min_rows: int) -> pd.DataFrame:
        df = self._cache.load(ticker, start, end, interval)
        if df.empty or len(df) < min_rows:
            raise ValueError(
                f"Insufficient data for {ticker} ({interval}): "
                f"got {len(df)} rows in cache, need ≥ {min_rows}"
            )
        return df

    def fetch_daily(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return self._load(ticker, start, end, "1d", 100)

    def fetch_weekly(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return self._load(ticker, start, end, "1wk", 42)


class DataFetchError(RuntimeError):
    """Raised when yfinance fails after all retries and no cache fallback exists."""


DEFAULT_PROVIDER = YFinanceProvider()
