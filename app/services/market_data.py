from datetime import datetime, timedelta, timezone

import yfinance as yf

from app.config import HISTORY_PERIOD, STALENESS_HOURS
from app.database import get_db


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
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=HISTORY_PERIOD)

    if hist.empty:
        raise ValueError(f"No data found for {symbol}")

    info = ticker.info
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    conn.execute(
        """INSERT INTO tickers (symbol, company_name, sector, market_cap, last_updated)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (symbol) DO UPDATE SET
             company_name = EXCLUDED.company_name,
             sector       = EXCLUDED.sector,
             market_cap   = EXCLUDED.market_cap,
             last_updated = EXCLUDED.last_updated""",
        (
            symbol,
            info.get("longName"),
            info.get("sector"),
            info.get("marketCap"),
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
