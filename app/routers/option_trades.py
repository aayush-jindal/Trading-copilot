"""
Options trade tracker endpoints.

POST   /option-trades/         — open a trade from a priced chain scan signal
GET    /option-trades/         — list open option trades with live repricing
DELETE /option-trades/{id}     — close a trade
GET    /option-trades/{id}/reprice — reprice one trade at current spot/IV
"""
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.dependencies import get_current_user
from app.models import OptionTradeCreate, OptionTradeResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/option-trades", tags=["option-trades"])

# BS pricing shim — same pattern used by chain scanner
_SRC = str(Path(__file__).resolve().parent.parent / "services" / "options" / "pricing" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _bs_price(spot: float, strike: float, t_years: float, iv: float,
              option_type: str, r: float = 0.045) -> float:
    """Price a single option via Black-Scholes."""
    try:
        from black_scholes import price_bs
        return float(price_bs(spot, strike, t_years, r, iv, option_type))
    except Exception:
        return 0.0


def _reprice_trade(row: dict) -> OptionTradeResponse:
    """Reprice a trade row at current spot and compute P&L + alerts."""
    legs = row["legs"] if isinstance(row["legs"], list) else json.loads(row["legs"])
    expiry_dt = datetime.strptime(row["expiry"], "%Y-%m-%d").date()
    dte_remaining = max((expiry_dt - date.today()).days, 0)
    t_years = dte_remaining / 365.0

    # Fetch current spot
    current_value = None
    try:
        from app.services.market_data import get_or_refresh_data
        _, price_list, _ = get_or_refresh_data(row["ticker"])
        spot = price_list[-1]["close"] if price_list else None
    except Exception:
        spot = None

    current_pnl = None
    pnl_pct = None
    exit_alert = None

    if spot and t_years > 0 and legs:
        net_value = 0.0
        for leg in legs:
            iv = leg.get("iv", 0.30)
            strike = leg.get("strike", 0)
            opt_type = leg.get("option_type", "call")
            leg_price = _bs_price(spot, strike, t_years, iv, opt_type)
            sign = 1.0 if leg.get("action") == "buy" else -1.0
            net_value += sign * leg_price

        current_value = round(abs(net_value), 4)
        entry = float(row["entry_premium"])
        is_credit = row["is_credit"]

        if is_credit:
            current_pnl = round(entry - current_value, 4)
        else:
            current_pnl = round(current_value - entry, 4)

        if entry > 0:
            pnl_pct = round((current_pnl / entry) * 100, 2)

        # Exit alerts
        max_loss = row.get("max_loss")
        max_profit = row.get("max_profit")
        exit_target = row.get("exit_target")

        if max_loss and current_pnl < 0 and abs(current_pnl) >= 0.8 * abs(max_loss):
            exit_alert = "APPROACHING_STOP"
        elif max_profit and current_pnl > 0 and current_pnl >= 0.8 * max_profit:
            exit_alert = "AT_TARGET"
        elif exit_target and is_credit and current_value <= exit_target:
            exit_alert = "AT_TARGET"
        elif exit_target and not is_credit and current_value >= exit_target:
            exit_alert = "AT_TARGET"

        if not exit_alert and dte_remaining < 7:
            exit_alert = "EXPIRY_WARNING"
        elif not exit_alert and dte_remaining < 14 and not is_credit:
            exit_alert = "THETA_DECAY"

    return OptionTradeResponse(
        id=row["id"],
        ticker=row["ticker"],
        strategy=row["strategy"],
        is_credit=row["is_credit"],
        legs=legs,
        entry_premium=row["entry_premium"],
        exit_target=row.get("exit_target"),
        option_stop=row.get("option_stop"),
        max_profit=row.get("max_profit"),
        max_loss=row.get("max_loss"),
        expiry=row["expiry"],
        dte_remaining=dte_remaining,
        entry_date=str(row["entry_date"]),
        status=row["status"],
        current_value=current_value,
        current_pnl=current_pnl,
        pnl_pct=pnl_pct,
        exit_alert=exit_alert,
        conviction=row.get("conviction"),
        iv_regime=row.get("iv_regime"),
    )


@router.post("/", status_code=201)
def open_trade(
    trade: OptionTradeCreate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    try:
        db.execute("""
            INSERT INTO option_trades
            (user_id, ticker, strategy, is_credit, legs, entry_premium,
             exit_target, option_stop, max_profit, max_loss, spread_width,
             expiry, dte_at_open, chain_iv, iv_rank, iv_regime, conviction, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            user["id"], trade.ticker, trade.strategy, trade.is_credit,
            json.dumps(trade.legs), trade.entry_premium,
            trade.exit_target, trade.option_stop, trade.max_profit,
            trade.max_loss, trade.spread_width,
            trade.expiry, trade.dte_at_open,
            trade.chain_iv, trade.iv_rank, trade.iv_regime,
            trade.conviction, trade.notes,
        ))
        row = db.execute("SELECT * FROM option_trades WHERE id = lastval()").fetchone()
        db.commit()
    finally:
        db.close()

    return _reprice_trade(dict(row))


@router.get("/")
def list_trades(
    status: str = Query("open"),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    try:
        rows = db.execute("""
            SELECT * FROM option_trades
            WHERE user_id = %s AND status = %s
            ORDER BY created_at DESC
        """, (user["id"], status)).fetchall()
    finally:
        db.close()

    return [_reprice_trade(dict(r)) for r in rows]


@router.delete("/{trade_id}")
def close_trade(
    trade_id: int,
    exit_price: Optional[float] = Query(None),
    exit_reason: Optional[str] = Query(None, max_length=100),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM option_trades WHERE id = %s AND user_id = %s",
            (trade_id, user["id"]),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Trade not found")
        if row["status"] != "open":
            raise HTTPException(status_code=400, detail="Trade already closed")

        db.execute("""
            UPDATE option_trades
            SET status = 'closed', exit_date = CURRENT_DATE,
                exit_price = %s, exit_reason = %s
            WHERE id = %s
        """, (exit_price, exit_reason or "manual_close", trade_id))
        db.commit()
    finally:
        db.close()

    return {"status": "closed", "trade_id": trade_id}


@router.get("/{trade_id}/reprice")
def reprice_trade(
    trade_id: int,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM option_trades WHERE id = %s AND user_id = %s",
            (trade_id, user["id"]),
        ).fetchone()
    finally:
        db.close()

    if not row:
        raise HTTPException(status_code=404, detail="Trade not found")

    return _reprice_trade(dict(row))
