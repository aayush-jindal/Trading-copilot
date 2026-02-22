"""
Management commands for the Trading Copilot.

Usage:
    python -m app.management backfill [TICKER ...]

    backfill          - re-fetch 6Y history for all tickers in the DB
    backfill AAPL     - re-fetch 6Y history for AAPL only
    backfill AAPL MSFT TSLA - backfill multiple tickers
"""

import sys

from app.database import get_db
from app.services.market_data import fetch_ticker_data


def backfill(tickers: list[str]) -> None:
    if not tickers:
        conn = get_db()
        rows = conn.execute("SELECT symbol FROM tickers ORDER BY symbol").fetchall()
        conn.close()
        tickers = [r["symbol"] for r in rows]

    if not tickers:
        print("No tickers found in DB. Pass at least one ticker symbol.")
        sys.exit(1)

    print(f"Backfilling {len(tickers)} ticker(s): {', '.join(tickers)}")
    for symbol in tickers:
        symbol = symbol.upper()
        print(f"  [{symbol}] fetching...", end=" ", flush=True)
        try:
            fetch_ticker_data(symbol)
            print("done")
        except Exception as e:
            print(f"ERROR: {e}")

    print("Backfill complete.")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] != "backfill":
        print(__doc__)
        sys.exit(1)

    tickers = args[1:]
    backfill(tickers)


if __name__ == "__main__":
    main()
