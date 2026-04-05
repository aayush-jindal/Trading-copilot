"""
Options chain scanner endpoint.

GET /options/chain-scan  — scans watchlist or provided tickers for
                           high-conviction options trade signals.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user
from app.database import get_db
from app.services.options.chain_scanner import scan_watchlist, OptionSignal
from app.services.options.chain_scanner.providers import create_provider
from app.services.options.config import CHAIN_SCANNER_CONFIG
from app.services.options.chain_scanner.strategy_mapper import map_signal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/options", tags=["options"])


@router.get("/chain-scan")
def chain_scan(
    tickers: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    # Resolve tickers
    if tickers:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        db = get_db()
        try:
            rows = db.execute(
                "SELECT ticker_symbol FROM watchlists WHERE user_id = %s",
                (user["id"],),
            ).fetchall()
            ticker_list = [r["ticker_symbol"] for r in rows]
        finally:
            db.close()

    if not ticker_list:
        return {"signals": [], "total": 0, "tickers_scanned": 0}

    provider = create_provider()
    signals = scan_watchlist(ticker_list, provider=provider, config=CHAIN_SCANNER_CONFIG)

    _save_signals(signals, user["id"])

    return {
        "signals": [_to_dict(s) for s in signals[:top]],
        "total": len(signals),
        "tickers_scanned": len(ticker_list),
    }


def _to_dict(s: OptionSignal) -> dict:
    rec = map_signal(s)
    base = {
        "ticker": s.ticker, "strike": s.strike, "expiry": s.expiry,
        "option_type": s.option_type, "dte": s.dte,
        "spot": s.spot, "bid": s.bid, "ask": s.ask, "mid": s.mid,
        "open_interest": s.open_interest,
        "bid_ask_spread_pct": s.bid_ask_spread_pct,
        "chain_iv": round(s.chain_iv, 4),
        "iv_rank": s.iv_rank, "iv_percentile": s.iv_percentile,
        "iv_regime": s.iv_regime,
        "garch_vol": round(s.garch_vol, 4),
        "theo_price": round(s.theo_price, 4),
        "edge_pct": s.edge_pct, "direction": s.direction,
        "delta": s.delta, "gamma": s.gamma,
        "theta": s.theta, "vega": s.vega,
        "conviction": s.conviction,
        "recommended_strategy": {
            "strategy": rec.strategy,
            "label": rec.strategy_label,
            "rationale": rec.rationale,
            "legs": rec.legs,
            "suggested_dte": rec.suggested_dte,
            "risk_profile": rec.risk_profile,
            "edge_source": rec.edge_source,
        } if rec else None,
    }
    return base


def _save_signals(signals: list, user_id: int):
    if not signals:
        return
    db = get_db()
    try:
        for s in signals:
            db.execute("""
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
        db.commit()
    except Exception as e:
        logger.error("Failed to save option signals: %s", e)
    finally:
        db.close()
