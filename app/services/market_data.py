import time
from datetime import datetime, timedelta, timezone

import yfinance as yf

from app.config import HISTORY_PERIOD, STALENESS_HOURS
from app.database import get_db

_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_WAIT    = 8  # seconds between retries


def is_data_stale(symbol: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT last_updated FROM tickers WHERE symbol = %s", (symbol,)
    ).fetchone()
    conn.close()

    if row is None or row["last_updated"] is None:
        return True

    last_updated = datetime.fromisoformat(row["last_updated"])
    return datetime.now(timezone.utc) - last_updated > timedelta(hours=STALENESS_HOURS)


def fetch_ticker_data(symbol: str) -> None:
    last_err: Exception | None = None
    for attempt in range(_RATE_LIMIT_RETRIES):
        try:
            return _fetch_once(symbol)
        except Exception as e:
            msg = str(e).lower()
            if "rate" in msg or "too many" in msg or "429" in msg:
                last_err = e
                time.sleep(_RATE_LIMIT_WAIT * (attempt + 1))
            else:
                raise
    raise last_err or RuntimeError(f"Failed to fetch {symbol} after {_RATE_LIMIT_RETRIES} attempts")


def _fetch_once(symbol: str) -> None:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=HISTORY_PERIOD)

    if hist.empty:
        raise ValueError(f"No data found for {symbol}")

    # ticker.info is best-effort — Yahoo Finance rate-limits this endpoint
    # aggressively from cloud IPs. Price data is what matters; metadata is nice-to-have.
    company_name = sector = market_cap = None
    try:
        info = ticker.info
        company_name = info.get("longName")
        sector       = info.get("sector")
        market_cap   = info.get("marketCap")
    except Exception:
        pass

    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    conn.execute(
        """INSERT INTO tickers (symbol, company_name, sector, market_cap, last_updated)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (symbol) DO UPDATE SET
             company_name = COALESCE(EXCLUDED.company_name, tickers.company_name),
             sector       = COALESCE(EXCLUDED.sector,       tickers.sector),
             market_cap   = COALESCE(EXCLUDED.market_cap,   tickers.market_cap),
             last_updated = EXCLUDED.last_updated""",
        (
            symbol,
            company_name,
            sector,
            market_cap,
            now,
        ),
    )

    rows = []
    for date, row in hist.iterrows():
        rows.append((
            symbol,
            date.strftime("%Y-%m-%d"),
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            float(row.get("Adj Close", row["Close"])),
            int(row["Volume"]),
        ))

    conn.executemany(
        """INSERT INTO price_history (ticker_symbol, date, open, high, low, close, adj_close, volume)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (ticker_symbol, date) DO UPDATE SET
             open      = EXCLUDED.open,
             high      = EXCLUDED.high,
             low       = EXCLUDED.low,
             close     = EXCLUDED.close,
             adj_close = EXCLUDED.adj_close,
             volume    = EXCLUDED.volume""",
        rows,
    )
    conn.commit()
    conn.close()

    # Weekly data is best-effort — a failure here must not break the daily fetch
    try:
        _upsert_weekly_data(symbol, ticker)
    except Exception:
        pass


def _upsert_weekly_data(symbol: str, ticker) -> None:
    """Fetch 2 years of weekly OHLCV and upsert into weekly_price_history."""
    hist = ticker.history(period="2y", interval="1wk")
    if hist.empty:
        return

    rows = []
    for date, row in hist.iterrows():
        rows.append((
            symbol,
            date.strftime("%Y-%m-%d"),
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            float(row.get("Adj Close", row["Close"])),
            int(row["Volume"]),
        ))

    conn = get_db()
    conn.executemany(
        """INSERT INTO weekly_price_history (ticker_symbol, date, open, high, low, close, adj_close, volume)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (ticker_symbol, date) DO UPDATE SET
             open      = EXCLUDED.open,
             high      = EXCLUDED.high,
             low       = EXCLUDED.low,
             close     = EXCLUDED.close,
             adj_close = EXCLUDED.adj_close,
             volume    = EXCLUDED.volume""",
        rows,
    )
    conn.commit()
    conn.close()


def fetch_weekly_data(symbol: str) -> None:
    """Publicly callable: fetch and store 2 years of weekly OHLCV for symbol."""
    ticker = yf.Ticker(symbol)
    _upsert_weekly_data(symbol, ticker)


def get_weekly_prices(symbol: str) -> list[dict]:
    """Return cached weekly OHLCV rows for symbol, ordered oldest-first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM weekly_price_history WHERE ticker_symbol = %s ORDER BY date",
        (symbol,),
    ).fetchall()
    conn.close()
    return [
        {
            "date": r["date"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "adj_close": r["adj_close"],
            "volume": r["volume"],
        }
        for r in rows
    ]


def get_or_refresh_data(symbol: str) -> tuple[dict, list[dict], str]:
    symbol = symbol.upper()
    stale = is_data_stale(symbol)
    source = "cache"

    if stale:
        fetch_ticker_data(symbol)
        source = "fetched"

    conn = get_db()
    ticker_row = conn.execute(
        "SELECT * FROM tickers WHERE symbol = %s", (symbol,)
    ).fetchone()

    prices = conn.execute(
        "SELECT * FROM price_history WHERE ticker_symbol = %s ORDER BY date",
        (symbol,),
    ).fetchall()
    conn.close()

    ticker_info = {
        "symbol": ticker_row["symbol"],
        "company_name": ticker_row["company_name"],
        "sector": ticker_row["sector"],
        "market_cap": ticker_row["market_cap"],
    }

    price_list = [
        {
            "date": p["date"],
            "open": p["open"],
            "high": p["high"],
            "low": p["low"],
            "close": p["close"],
            "adj_close": p["adj_close"],
            "volume": p["volume"],
        }
        for p in prices
    ]

    return ticker_info, price_list, source


def get_latest_prices(symbol: str, days: int = 30) -> tuple[dict, list[dict], str]:
    ticker_info, all_prices, source = get_or_refresh_data(symbol)
    return ticker_info, all_prices[-days:], source
