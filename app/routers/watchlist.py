from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.services.market_data import get_or_refresh_data
from app.services.ta_engine import analyze_ticker, _prepare_dataframe

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistItem(BaseModel):
    ticker_symbol: str
    date_added: str


class WatchlistDashboardItem(BaseModel):
    ticker_symbol: str
    company_name: str | None
    price: float | None
    day_change: float | None
    day_change_pct: float | None
    trend_signal: str | None


# ── List watchlist ────────────────────────────────────────────────────────────

@router.get("", response_model=list[WatchlistItem])
def get_watchlist(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT ticker_symbol, date_added FROM watchlists WHERE user_id = %s ORDER BY date_added DESC",
        (user["id"],),
    ).fetchall()
    conn.close()
    return [{"ticker_symbol": r["ticker_symbol"], "date_added": r["date_added"]} for r in rows]


# ── Dashboard (price + signal per ticker) ─────────────────────────────────────

@router.get("/dashboard", response_model=list[WatchlistDashboardItem])
def get_watchlist_dashboard(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT ticker_symbol FROM watchlists WHERE user_id = %s ORDER BY date_added DESC",
        (user["id"],),
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        symbol = row["ticker_symbol"]
        try:
            ticker_info, price_list, _ = get_or_refresh_data(symbol)
            if len(price_list) < 2:
                raise ValueError("insufficient data")

            last  = price_list[-1]["close"]
            prev  = price_list[-2]["close"]
            day_change     = last - prev
            day_change_pct = (day_change / prev * 100) if prev else None

            df = _prepare_dataframe(price_list)
            analysis = analyze_ticker(df, symbol, last)
            trend_signal = analysis["trend"]["signal"]
        except Exception:
            last = day_change = day_change_pct = trend_signal = None
            ticker_info = {"company_name": None}

        results.append(WatchlistDashboardItem(
            ticker_symbol=symbol,
            company_name=ticker_info.get("company_name"),
            price=last,
            day_change=day_change,
            day_change_pct=day_change_pct,
            trend_signal=trend_signal,
        ))
    return results


# ── Add ticker ────────────────────────────────────────────────────────────────

@router.post("/{ticker}", status_code=201)
def add_to_watchlist(ticker: str, user: dict = Depends(get_current_user)):
    symbol = ticker.upper()
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO watchlists (user_id, ticker_symbol, date_added)
               VALUES (%s, %s, %s)
               ON CONFLICT (user_id, ticker_symbol) DO NOTHING""",
            (user["id"], symbol, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ticker_symbol": symbol, "status": "added"}


# ── Remove ticker ─────────────────────────────────────────────────────────────

@router.delete("/{ticker}")
def remove_from_watchlist(ticker: str, user: dict = Depends(get_current_user)):
    symbol = ticker.upper()
    conn = get_db()
    result = conn.execute(
        "DELETE FROM watchlists WHERE user_id = %s AND ticker_symbol = %s",
        (user["id"], symbol),
    )
    conn.commit()
    conn.close()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    return {"ticker_symbol": symbol, "status": "removed"}
