"""Nightly digest and morning briefing generation.

Functions in this module are called from a cron job (not a FastAPI request),
so they use get_db() directly rather than FastAPI's Depends(get_db).

Public API:
    generate_digest_for_user(user_id)    — one-line TA summary per watchlist ticker
    save_digest_notification(user_id, digest) — persist digest as a notification
    generate_strategy_briefing(user_id)  — ENTRY setups from live strategy scan
    generate_trade_alerts(user_id)       — exit alerts for open trades
    run_nightly_refresh()                — orchestrates data refresh + all digests
"""

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


def generate_strategy_briefing(user_id: int) -> str:
    """
    Scan user's watchlist for ENTRY setups. Returns formatted plain text.
    Uses parallel ThreadPoolExecutor — same pattern as /scan/watchlist endpoint.
    Returns empty string if watchlist is empty or no ENTRY setups found.
    DB connection follows same pattern as rest of digest.py.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from backtesting.scanner import StrategyScanner
    from app.routers.strategies import _get_user_watchlist, _get_user_settings

    tickers = _get_user_watchlist(user_id)
    if not tickers:
        return ""

    account_size, risk_pct = _get_user_settings(user_id)
    scanner = StrategyScanner()
    all_results = []

    def _scan_one(ticker):
        try:
            results = scanner.scan(ticker, account_size, risk_pct)
            for r in results:
                r.ticker = ticker
            return results
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=min(len(tickers), 10)) as pool:
        for future in as_completed(pool.submit(_scan_one, t) for t in tickers):
            all_results.extend(future.result())

    entries = [r for r in all_results if r.verdict == "ENTRY"]
    entries.sort(key=lambda r: r.score, reverse=True)

    if not entries:
        return ""

    from datetime import date
    lines = [f"STRATEGY SETUPS — {date.today()}", ""]
    for r in entries:
        lines.append(f"{r.ticker}  {r.name} — Score {r.score}/100")
        if r.risk:
            target = getattr(r.risk, "target", None) or getattr(r.risk, "target_1", None)
            lines.append(
                f"  Entry: ${r.risk.entry_price:.2f}  "
                f"Stop: ${r.risk.stop_loss:.2f}  "
                f"Target: ${target:.2f}  "
                f"R:R: {r.risk.risk_reward:.1f}x"
            )
            if r.risk.position_size:
                lines.append(
                    f"  Shares: {r.risk.position_size} "
                    f"(${account_size:,.0f} account, {risk_pct:.0%} risk)"
                )
        lines.append("")

    return "\n".join(lines)


def generate_trade_alerts(user_id: int) -> str:
    """
    Check all open trades for exit conditions.
    Returns formatted alert string. Empty string if no alerts.
    """
    from datetime import date

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM open_trades WHERE user_id = %s AND status = 'open'",
        (user_id,),
    ).fetchall()
    conn.close()

    if not rows:
        return ""

    alerts = []
    for row in rows:
        ticker = row["ticker"]
        strategy = row["strategy_name"]
        entry = float(row["entry_price"])
        stop = float(row["stop_loss"])
        target = float(row["target"])

        try:
            _, price_list, _ = get_or_refresh_data(ticker)
            cp = price_list[-1]["close"] if price_list else None
        except Exception:
            cp = None

        if cp is None:
            continue

        if cp <= stop * 1.02:
            alerts.append(
                f"\u26a0 {ticker} {strategy}: approaching stop"
                f" \u2014 current ${cp:.2f}  stop ${stop:.2f}"
            )
        elif cp >= target * 0.98:
            alerts.append(
                f"\u2713 {ticker} {strategy}: at target"
                f" \u2014 current ${cp:.2f}  target ${target:.2f}"
            )

    if not alerts:
        return ""

    lines = [f"OPEN TRADE ALERTS \u2014 {date.today()}", ""] + alerts
    return "\n".join(lines)


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
