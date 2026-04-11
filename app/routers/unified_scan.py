"""Unified equity + options signal scanner.

GET /scan/unified  — scans user's watchlist through both the equity strategy
                     scanner and the chain scanner, merges results, boosts
                     conviction when both fire, and suggests hedges.

Phase F — Equity + Options Signal Correlation
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.dependencies import get_current_user
from app.routers.strategies import _get_user_settings, _get_user_watchlist, _result_to_dict
from app.services.options.chain_scanner import scan_watchlist as chain_scan_watchlist, OptionSignal
from app.services.options.chain_scanner.providers import create_provider
from app.services.options.config import CHAIN_SCANNER_CONFIG
from app.services.options.chain_scanner.strategy_mapper import map_signal
from backtesting.scanner import StrategyScanner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan", tags=["unified-scan"])

# Conviction boost when both equity + options signals fire for same ticker
_CORRELATION_BOOST = 1.15


@router.get("/unified")
def unified_scan(
    top: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Scan watchlist through both equity and options scanners, merge results.

    Returns a ranked list of unified signals. When both an equity strategy
    and an options signal fire for the same ticker, the options signal's
    conviction is boosted by 15% and the correlated equity signal is attached.

    Also checks for hedge opportunities: if the user has an open equity trade
    and the chain scanner finds LOW IV regime options, suggests a protective
    put or put spread.
    """
    tickers = _get_user_watchlist(user["id"])
    if not tickers:
        return {"signals": [], "total": 0, "tickers_scanned": 0}

    # Run both scanners in parallel
    equity_results = []
    option_signals = []

    account_size, risk_pct = _get_user_settings(user["id"])

    def _scan_equity():
        scanner = StrategyScanner()

        def _scan_one(ticker: str) -> list:
            try:
                results = scanner.scan(ticker, account_size, risk_pct)
                for r in results:
                    r.ticker = ticker
                return results
            except Exception as e:
                logger.debug("Equity scanner skip %s: %s", ticker, e)
                return []

        all_results = []
        with ThreadPoolExecutor(max_workers=min(len(tickers), 10)) as pool:
            futures = {pool.submit(_scan_one, t): t for t in tickers}
            for future in as_completed(futures):
                all_results.extend(future.result())
        return all_results

    def _scan_options():
        try:
            provider = create_provider(delay=0.5)
            return chain_scan_watchlist(tickers, provider=provider, config=CHAIN_SCANNER_CONFIG)
        except Exception as e:
            logger.error("Chain scanner failed: %s", e)
            return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        eq_future = pool.submit(_scan_equity)
        opt_future = pool.submit(_scan_options)
        equity_results = eq_future.result()
        option_signals = opt_future.result()

    # Group by ticker
    equity_by_ticker: dict[str, list] = {}
    for r in equity_results:
        ticker = getattr(r, "ticker", None)
        if ticker:
            equity_by_ticker.setdefault(ticker, []).append(r)

    options_by_ticker: dict[str, list[OptionSignal]] = {}
    for s in option_signals:
        options_by_ticker.setdefault(s.ticker, []).append(s)

    # Fetch open equity trades for hedge suggestions
    open_trade_tickers = _get_open_equity_tickers(user["id"])

    # Build unified signal list
    unified = []

    # Emit equity signals
    for r in equity_results:
        ticker = getattr(r, "ticker", None)
        d = _result_to_dict(r)
        d["signal_source"] = "equity"
        d["correlated_option_signal"] = ticker in options_by_ticker
        unified.append(d)

    # Emit option signals with correlation boost + hedge suggestions
    for s in option_signals:
        correlated_equity = equity_by_ticker.get(s.ticker)
        conviction = s.conviction

        correlated_name = None
        if correlated_equity:
            # Boost conviction when both scanners fire
            conviction = min(conviction * _CORRELATION_BOOST, 100)
            # Pick best equity signal (highest score)
            best_eq = max(correlated_equity, key=lambda r: r.score)
            correlated_name = best_eq.name

        rec = map_signal(s)
        d = {
            "signal_source": "options",
            "ticker": s.ticker,
            "strike": s.strike,
            "expiry": s.expiry,
            "option_type": s.option_type,
            "dte": s.dte,
            "spot": s.spot,
            "bid": s.bid,
            "ask": s.ask,
            "mid": s.mid,
            "open_interest": s.open_interest,
            "bid_ask_spread_pct": s.bid_ask_spread_pct,
            "chain_iv": round(s.chain_iv, 4),
            "iv_rank": s.iv_rank,
            "iv_percentile": s.iv_percentile,
            "iv_regime": s.iv_regime,
            "garch_vol": round(s.garch_vol, 4),
            "theo_price": round(s.theo_price, 4),
            "edge_pct": s.edge_pct,
            "direction": s.direction,
            "delta": s.delta,
            "gamma": s.gamma,
            "theta": s.theta,
            "vega": s.vega,
            "conviction": round(conviction, 2),
            "correlated_equity_signal": correlated_name,
            "recommended_strategy": {
                "strategy": rec.strategy,
                "label": rec.strategy_label,
                "rationale": rec.rationale,
            } if rec else None,
            "hedge_suggestion": None,
        }

        # Hedge suggestion: user has open long equity trade + LOW IV puts available
        if (
            s.ticker in open_trade_tickers
            and s.iv_regime == "LOW"
            and s.option_type == "put"
            and s.direction == "BUY"
        ):
            d["hedge_suggestion"] = (
                f"Protective put available — IV is LOW ({s.iv_rank:.0f}th rank). "
                f"Consider {s.ticker} ${s.strike:.0f}P {s.expiry} "
                f"at ${s.mid:.2f} to hedge your open equity position."
            )

        unified.append(d)

    # Sort: correlated signals first, then by conviction/score descending
    def _sort_key(d: dict) -> tuple:
        is_correlated = 1 if d.get("correlated_equity_signal") or d.get("correlated_option_signal") else 0
        score = d.get("conviction") or d.get("score") or 0
        return (is_correlated, score)

    unified.sort(key=_sort_key, reverse=True)

    return {
        "signals": unified[:top],
        "total": len(unified),
        "tickers_scanned": len(tickers),
        "equity_count": len(equity_results),
        "options_count": len(option_signals),
    }


def _get_open_equity_tickers(user_id: int) -> set[str]:
    """Return set of tickers with open equity trades for this user."""
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM open_trades WHERE user_id = %s AND status = 'open'",
            (user_id,),
        ).fetchall()
        conn.close()
        return {r["ticker"] for r in rows}
    except Exception:
        return set()
