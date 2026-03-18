"""
OHLCV data cache backed by SQLite.

Stores fetched data persistently so reruns never re-download what we already have.
Only the gap between cached coverage and the requested range is fetched from yfinance.

DB file: backtesting/ohlcv.db
  — included in `docker cp backtesting/ container:/app/` automatically
  — after each run: `docker cp container:/app/backtesting/ohlcv.db ./backtesting/`
    to pull new rows back to the host

Table: ohlcv (ticker, date, interval, open, high, low, close, volume)
  PRIMARY KEY (ticker, date, interval) — upsert-safe
"""

import os
import sqlite3
from typing import Optional

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohlcv.db")


class DataCache:
    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent workers
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv (
                    ticker   TEXT    NOT NULL,
                    date     TEXT    NOT NULL,
                    interval TEXT    NOT NULL DEFAULT '1d',
                    open     REAL,
                    high     REAL,
                    low      REAL,
                    close    REAL,
                    volume   REAL,
                    PRIMARY KEY (ticker, date, interval)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tkr_iv_dt "
                "ON ohlcv (ticker, interval, date)"
            )

    # ── read ──────────────────────────────────────────────────────────────────

    def coverage(self, ticker: str, interval: str = "1d") -> Optional[tuple]:
        """Return (min_date_str, max_date_str) of cached rows, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MIN(date), MAX(date) FROM ohlcv WHERE ticker=? AND interval=?",
                (ticker, interval),
            ).fetchone()
        return (row[0], row[1]) if row and row[0] else None

    def load(self, ticker: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
        """Return cached rows in [start, end] as a DatetimeIndex DataFrame."""
        with self._connect() as conn:
            df = pd.read_sql(
                "SELECT date, open, high, low, close, volume FROM ohlcv "
                "WHERE ticker=? AND interval=? AND date>=? AND date<=? "
                "ORDER BY date",
                conn,
                params=(ticker, interval, start, end),
            )
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df

    # ── write ─────────────────────────────────────────────────────────────────

    def upsert(self, ticker: str, df: pd.DataFrame, interval: str = "1d") -> None:
        """Persist a DataFrame to the cache (INSERT OR REPLACE)."""
        if df is None or df.empty:
            return
        rows = []
        for date, row in df.iterrows():
            rows.append((
                ticker,
                str(date.date()),
                interval,
                float(row.get("open")  or 0),
                float(row.get("high")  or 0),
                float(row.get("low")   or 0),
                float(row.get("close") or 0),
                float(row.get("volume") or 0),
            ))
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO ohlcv "
                "(ticker, date, interval, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )


# Module-level singleton — shared across all DataProvider instances in a process
_cache = DataCache()
