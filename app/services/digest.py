import json
from datetime import datetime, timezone

from app.database import get_db
from app.services.market_data import fetch_ticker_data, get_or_refresh_data, get_weekly_prices
from app.services.ta_engine import analyze_ticker, _prepare_dataframe


def _ticker_summary(symbol: str) -> str:
    """One-line summary for a ticker: 'AAPL → Bullish. RSI cooling from overbought.'"""
    ticker_info, price_list, _ = get_or_refresh_data(symbol)
    if len(price_list) < 200:  # matches analyze_ticker minimum bar requirement
        return f"{symbol} → Insufficient data for analysis."

    last = price_list[-1]["close"]
    weekly_price_list = get_weekly_prices(symbol)
    df = _prepare_dataframe(price_list)
    analysis = analyze_ticker(df, symbol, last, weekly_price_list)

    trend   = analysis["trend"]["signal"]
    rsi     = analysis["momentum"].get("rsi")
    rsi_sig = analysis["momentum"].get("rsi_signal", "")
    macd    = analysis["momentum"].get("macd_crossover", "none")

    parts = [f"{symbol} → {trend.title()}."]
    if rsi is not None:
        parts.append(f"RSI {rsi:.0f} ({rsi_sig.replace('_', ' ').lower()}).")
    if macd != "none":
        parts.append(f"MACD {macd.replace('_', ' ')}.")

    return " ".join(parts)


def generate_digest_for_user(user_id: int) -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT ticker_symbol FROM watchlists WHERE user_id = %s ORDER BY date_added",
        (user_id,),
    ).fetchall()
    conn.close()

    date_str = datetime.now(timezone.utc).strftime("%b %-d")
    entries = []
    for row in rows:
        symbol = row["ticker_symbol"]
        try:
            summary = _ticker_summary(symbol)
        except Exception as e:
            summary = f"{symbol} → Error: {e}"
        entries.append({"ticker": symbol, "summary": summary})

    return {"date": date_str, "entries": entries}


def save_digest_notification(user_id: int, digest: dict) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO notifications (user_id, content, created_at, is_read) VALUES (%s, %s, %s, FALSE)",
        (user_id, json.dumps(digest), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def run_nightly_refresh() -> dict:
    """
    1. Collect all unique watchlisted tickers
    2. Force-fetch fresh data for each
    3. Generate and save a digest notification for each user
    """
    import time
    start = time.time()

    conn = get_db()
    ticker_rows = conn.execute(
        "SELECT DISTINCT ticker_symbol FROM watchlists"
    ).fetchall()
    user_rows = conn.execute(
        "SELECT DISTINCT user_id FROM watchlists"
    ).fetchall()
    conn.close()

    tickers = [r["ticker_symbol"] for r in ticker_rows]
    user_ids = [r["user_id"] for r in user_rows]

    # Refresh market data for every watched ticker
    refresh_errors = 0
    for symbol in tickers:
        try:
            fetch_ticker_data(symbol)
        except Exception:
            refresh_errors += 1

    # Generate digest for each user
    for user_id in user_ids:
        try:
            digest = generate_digest_for_user(user_id)
            if digest["entries"]:
                save_digest_notification(user_id, digest)
        except Exception:
            pass

    return {
        "tickers_refreshed": len(tickers) - refresh_errors,
        "users_notified": len(user_ids),
        "duration_seconds": round(time.time() - start, 1),
    }
