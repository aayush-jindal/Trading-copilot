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

    # Store daily IV snapshots for iv_history
    _store_iv_snapshots(signals)

    # Reprice open option trades and generate exit alerts
    alerts_sent = _reprice_open_trades()

    # Phase G: high conviction + IV rank alerts
    conviction_alerts = _generate_high_conviction_alerts(signals)
    iv_alerts = _generate_iv_rank_alerts(signals)

    return {
        "options_signals": len(signals),
        "options_tickers": len(tickers),
        "options_errors": errors,
        "options_alerts": alerts_sent + conviction_alerts + iv_alerts,
        "options_duration": round(time.time() - start, 1),
    }


def _store_iv_snapshots(signals: list) -> None:
    """Extract ATM IV per ticker from scan signals and upsert into iv_history."""
    if not signals:
        return

    # Group signals by ticker
    by_ticker: dict[str, list] = {}
    for s in signals:
        by_ticker.setdefault(s.ticker, []).append(s)

    conn = get_db()
    for ticker, sigs in by_ticker.items():
        spot = sigs[0].spot
        # Find ATM call and put (closest to spot)
        calls = [s for s in sigs if s.direction == 'call' or getattr(s, 'option_type', '') == 'call']
        puts = [s for s in sigs if s.direction == 'put' or getattr(s, 'option_type', '') == 'put']

        atm_iv_call = None
        atm_iv_put = None

        if calls:
            atm_call = min(calls, key=lambda s: abs(s.strike - spot))
            atm_iv_call = atm_call.chain_iv
        if puts:
            atm_put = min(puts, key=lambda s: abs(s.strike - spot))
            atm_iv_put = atm_put.chain_iv

        # Compute average
        ivs = [v for v in [atm_iv_call, atm_iv_put] if v is not None]
        atm_iv_avg = sum(ivs) / len(ivs) if ivs else None

        if atm_iv_avg is None:
            continue

        try:
            conn.execute("""
                INSERT INTO iv_history
                    (ticker, scan_date, atm_iv_call, atm_iv_put, atm_iv_avg, spot)
                VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
                ON CONFLICT (ticker, scan_date) DO UPDATE
                SET atm_iv_call = EXCLUDED.atm_iv_call,
                    atm_iv_put = EXCLUDED.atm_iv_put,
                    atm_iv_avg = EXCLUDED.atm_iv_avg,
                    spot = EXCLUDED.spot
            """, (ticker, atm_iv_call, atm_iv_put, atm_iv_avg, spot))
        except Exception as e:
            logger.warning("Failed to store IV snapshot for %s: %s", ticker, e)

    conn.commit()
    conn.close()


def _reprice_open_trades() -> int:
    """Reprice all open option trades and notify users on exit alerts."""
    import json
    from datetime import datetime, timezone

    from app.routers.option_trades import _reprice_trade

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM option_trades WHERE status = 'open'"
    ).fetchall()
    conn.close()

    if not rows:
        return 0

    alerts_sent = 0
    for row in rows:
        try:
            result = _reprice_trade(dict(row))
            if result.exit_alert:
                conn = get_db()
                content = json.dumps({
                    "date": datetime.now(timezone.utc).strftime("%b %-d"),
                    "entries": [{
                        "ticker": result.ticker,
                        "summary": (
                            f"{result.ticker} {result.strategy}: {result.exit_alert} "
                            f"— P&L ${result.current_pnl:.2f} ({result.pnl_pct:+.1f}%)"
                            if result.current_pnl is not None
                            else f"{result.ticker} {result.strategy}: {result.exit_alert}"
                        ),
                    }],
                })
                conn.execute(
                    "INSERT INTO notifications (user_id, type, content, created_at, is_read) "
                    "VALUES (%s, %s, %s, %s, FALSE)",
                    (row["user_id"], "option_exit", content,
                     datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                conn.close()
                alerts_sent += 1
        except Exception as e:
            logger.warning("Failed to reprice trade %s: %s", row.get("id"), e)

    return alerts_sent


def _generate_high_conviction_alerts(signals: list) -> int:
    """Create notifications for signals with conviction > 70."""
    import json
    from datetime import datetime, timezone

    if not signals:
        return 0

    high_conv = [s for s in signals if s.conviction and s.conviction > 70]
    if not high_conv:
        return 0

    # Get user→tickers map so we only alert users watching the ticker
    conn = get_db()
    user_rows = conn.execute(
        "SELECT user_id, ticker_symbol FROM watchlists"
    ).fetchall()
    conn.close()

    user_tickers: dict[int, set[str]] = {}
    for r in user_rows:
        user_tickers.setdefault(r["user_id"], set()).add(r["ticker_symbol"])

    now_iso = datetime.now(timezone.utc).isoformat()
    date_str = datetime.now(timezone.utc).strftime("%b %-d")
    alerts_sent = 0

    # Group high-conviction signals by ticker for compact notifications
    by_ticker: dict[str, list] = {}
    for s in high_conv:
        by_ticker.setdefault(s.ticker, []).append(s)

    conn = get_db()
    for user_id, watched in user_tickers.items():
        entries = []
        for ticker in sorted(by_ticker):
            if ticker not in watched:
                continue
            best = max(by_ticker[ticker], key=lambda s: s.conviction)
            entries.append({
                "ticker": best.ticker,
                "summary": (
                    f"{best.direction.upper()} {best.option_type} "
                    f"${best.strike:.0f} — {best.conviction:.0f}% conviction "
                    f"({best.iv_regime} IV)"
                ),
            })

        if entries:
            content = json.dumps({"date": date_str, "entries": entries})
            conn.execute(
                "INSERT INTO notifications (user_id, type, content, created_at, is_read) "
                "VALUES (%s, %s, %s, %s, FALSE)",
                (user_id, "option_signal", content, now_iso),
            )
            alerts_sent += 1

    conn.commit()
    conn.close()
    return alerts_sent


def _generate_iv_rank_alerts(signals: list) -> int:
    """Create notifications when IV rank crosses above 80 or below 20."""
    import json
    from datetime import datetime, timezone

    if not signals:
        return 0

    # Deduplicate: one alert per ticker, using the first signal's IV rank
    seen: dict[str, float] = {}
    for s in signals:
        if s.ticker not in seen and s.iv_rank is not None:
            seen[s.ticker] = s.iv_rank

    # Filter to extreme IV rank tickers
    extreme = {t: rank for t, rank in seen.items() if rank >= 80 or rank <= 20}
    if not extreme:
        return 0

    conn = get_db()
    user_rows = conn.execute(
        "SELECT user_id, ticker_symbol FROM watchlists"
    ).fetchall()
    conn.close()

    user_tickers: dict[int, set[str]] = {}
    for r in user_rows:
        user_tickers.setdefault(r["user_id"], set()).add(r["ticker_symbol"])

    now_iso = datetime.now(timezone.utc).isoformat()
    date_str = datetime.now(timezone.utc).strftime("%b %-d")
    alerts_sent = 0

    conn = get_db()
    for user_id, watched in user_tickers.items():
        entries = []
        for ticker in sorted(extreme):
            if ticker not in watched:
                continue
            rank = extreme[ticker]
            label = "HIGH" if rank >= 80 else "LOW"
            entries.append({
                "ticker": ticker,
                "summary": f"IV Rank {rank:.0f} ({label}) — consider {('selling' if label == 'HIGH' else 'buying')} premium",
            })

        if entries:
            content = json.dumps({"date": date_str, "entries": entries})
            conn.execute(
                "INSERT INTO notifications (user_id, type, content, created_at, is_read) "
                "VALUES (%s, %s, %s, %s, FALSE)",
                (user_id, "iv_alert", content, now_iso),
            )
            alerts_sent += 1

    conn.commit()
    conn.close()
    return alerts_sent
