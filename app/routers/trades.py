"""Trade tracker endpoints.

Allows users to log open trades, view live P&L in R-multiples, and close trades.
All endpoints require JWT authentication.

Routes:
    POST   /trades/         — log a new trade
    GET    /trades/         — list open trades with live current_r and exit alerts
    DELETE /trades/{id}     — manually close a trade
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_user
from app.models import TradeCreate, TradeResponse
from app.services.market_data import get_or_refresh_data

router = APIRouter(prefix="/trades", tags=["trades"])


def _current_price(ticker: str) -> float | None:
    """Return the latest close price for ticker, or None on any error."""
    try:
        _, price_list, _ = get_or_refresh_data(ticker)
        return price_list[-1]["close"] if price_list else None
    except Exception:
        return None


def _compute_r(current_price: float, entry_price: float, stop_loss: float) -> float | None:
    """Express current P&L as R-multiples: 1R = distance from entry to stop.

    Returns None if entry == stop (invalid risk definition).
    Positive values = profitable; negative = in drawdown.
    """
    risk = entry_price - stop_loss
    if risk == 0:
        return None
    return round((current_price - entry_price) / risk, 3)


def _exit_alert(current_price: float, stop_loss: float, target: float) -> str | None:
    """Return an alert string if the trade is near its stop or target.

    Thresholds:
        APPROACHING_STOP — price within 2% of stop loss
        AT_TARGET        — price within 2% of target
    """
    if current_price <= stop_loss * 1.02:
        return "APPROACHING_STOP"
    if current_price >= target * 0.98:
        return "AT_TARGET"
    return None


def _row_to_response(row: dict) -> TradeResponse:
    """Convert a DB row dict to a TradeResponse, enriched with live price data."""
    cp = _current_price(row["ticker"])
    entry = float(row["entry_price"])
    stop = float(row["stop_loss"])
    target = float(row["target"])
    current_r = _compute_r(cp, entry, stop) if cp is not None else None
    alert = _exit_alert(cp, stop, target) if cp is not None else None
    return TradeResponse(
        id=row["id"],
        ticker=row["ticker"],
        strategy_name=row["strategy_name"],
        strategy_type=row["strategy_type"],
        entry_price=entry,
        stop_loss=stop,
        target=target,
        shares=row["shares"],
        entry_date=str(row["entry_date"]),
        current_price=cp,
        current_r=current_r,
        exit_alert=alert,
    )


@router.post("/", response_model=TradeResponse)
def log_trade(trade: TradeCreate, current_user=Depends(get_current_user)):
    """Log a new open trade for the authenticated user.

    Inserts the trade into open_trades, then fetches the live price to
    return an enriched TradeResponse including current_r and exit_alert.
    """
    conn = get_db()
    row = conn.execute(
        """
        INSERT INTO open_trades
            (user_id, ticker, strategy_name, strategy_type,
             entry_price, stop_loss, target, shares, risk_reward)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            current_user["id"],
            trade.ticker.upper(),
            trade.strategy_name,
            trade.strategy_type,
            trade.entry_price,
            trade.stop_loss,
            trade.target,
            trade.shares,
            trade.risk_reward,
        ),
    ).fetchone()
    conn.commit()
    conn.close()
    return _row_to_response(dict(row))


@router.get("/", response_model=list[TradeResponse])
def get_trades(current_user=Depends(get_current_user)):
    """Return all open trades for the authenticated user with live P&L.

    Each trade includes current_r (profit in R-multiples) and exit_alert
    if the price is approaching the stop or target.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM open_trades WHERE user_id = %s AND status = 'open' ORDER BY entry_date DESC",
        (current_user["id"],),
    ).fetchall()
    conn.close()
    return [_row_to_response(dict(r)) for r in rows]


@router.delete("/{trade_id}")
def close_trade(trade_id: int, current_user=Depends(get_current_user)):
    """Manually close an open trade.

    Sets status='closed', records exit_price (live price at close time)
    and exit_date. Returns 404 if trade not found, 403 if it belongs to
    a different user.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT id, user_id, ticker FROM open_trades WHERE id = %s",
        (trade_id,),
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Trade not found")
    if row["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Not your trade")

    cp = _current_price(row["ticker"])
    conn.execute(
        """
        UPDATE open_trades
        SET status = 'closed', exit_price = %s, exit_date = %s, exit_reason = 'manual'
        WHERE id = %s
        """,
        (cp, date.today(), trade_id),
    )
    conn.commit()
    conn.close()
    return {"closed": trade_id}
