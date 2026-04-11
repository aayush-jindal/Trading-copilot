"""
Nightly options chain scan.

Called from run_nightly_refresh() after equity data is fresh.
Scans all watchlisted tickers once, stores signals in option_signals.
"""
import logging
import time

from app.database import get_db

logger = logging.getLogger(__name__)


def run_nightly_chain_scan() -> dict:
    start = time.time()

    conn = get_db()
    ticker_rows = conn.execute(
        "SELECT DISTINCT ticker_symbol FROM watchlists"
    ).fetchall()
    user_rows = conn.execute(
        "SELECT user_id, ticker_symbol FROM watchlists"
    ).fetchall()
    conn.close()

    tickers = [r["ticker_symbol"] for r in ticker_rows]
    if not tickers:
        return {"options_signals": 0, "options_tickers": 0, "options_errors": 0}

    # Build user → tickers map
    user_tickers: dict[int, set[str]] = {}
    for r in user_rows:
        user_tickers.setdefault(r["user_id"], set()).add(r["ticker_symbol"])

    # Scan once with throttled provider (default 1s delay)
    from app.services.options.chain_scanner import scan_watchlist
    from app.services.options.chain_scanner.providers import create_provider

    provider = create_provider()  # CachedProvider wraps YFinanceProvider
    signals = []
    errors = 0

    try:
        signals = scan_watchlist(tickers, provider=provider)
    except Exception as e:
        logger.error("Nightly chain scan failed: %s", e)
        errors = 1

    # Store per user
    if signals:
        conn = get_db()
        for user_id, watched in user_tickers.items():
            for s in signals:
                if s.ticker not in watched:
                    continue
                try:
                    conn.execute("""
                        INSERT INTO option_signals
                        (user_id, ticker, strike, expiry, option_type, dte,
                         spot, bid, ask, mid, open_interest, bid_ask_spread_pct,
                         chain_iv, iv_rank, iv_percentile, iv_regime,
                         garch_vol, theo_price, edge_pct, direction,
                         delta, gamma, theta, vega, conviction)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        user_id, s.ticker, s.strike, s.expiry, s.option_type,
                        s.dte, s.spot, s.bid, s.ask, s.mid, s.open_interest,
                        s.bid_ask_spread_pct, s.chain_iv, s.iv_rank,
                        s.iv_percentile, s.iv_regime, s.garch_vol,
                        s.theo_price, s.edge_pct, s.direction,
                        s.delta, s.gamma, s.theta, s.vega, s.conviction,
                    ))
                except Exception:
                    errors += 1
        conn.commit()
        conn.close()

    return {
        "options_signals": len(signals),
        "options_tickers": len(tickers),
        "options_errors": errors,
        "options_duration": round(time.time() - start, 1),
    }
