"""Step 4: Fetch live market signals for a ticker.

Reuses the existing app services directly — no HTTP round-trip needed.
Requires DATABASE_URL to be set (same PostgreSQL instance as the main app).
"""

from __future__ import annotations


def get_live_signals(ticker: str) -> dict:
    """Return the full analyze_ticker result dict for *ticker*.

    Triggers a yfinance fetch if data is stale (>24 h).
    Includes swing_setup and weekly_trend exactly as the /analyze API does.

    Raises:
        ValueError: if fewer than 200 daily bars are available.
        RuntimeError: if the database is unreachable or yfinance fails.
    """
    # Lazy imports so the module loads even without a live DB during testing
    from app.services.market_data import get_or_refresh_data, get_weekly_prices
    from app.services.ta_engine import _prepare_dataframe, analyze_ticker

    ticker = ticker.upper()
    ticker_info, price_list, _ = get_or_refresh_data(ticker)

    weekly_price_list: list[dict] = []
    try:
        weekly_price_list = get_weekly_prices(ticker)
    except Exception:
        pass  # weekly data is best-effort

    df = _prepare_dataframe(price_list)
    price = float(df["close"].iloc[-1])
    result = analyze_ticker(df, ticker_info["symbol"], price, weekly_price_list)
    return result
