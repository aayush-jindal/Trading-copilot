from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_user
from app.models import UserSettings
from app.services.market_data import get_or_refresh_data
from backtesting.scanner import StrategyScanner

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _get_user_settings(user_id: int) -> tuple[float, float]:
    conn = get_db()
    row = conn.execute(
        "SELECT account_size, risk_pct FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return 10000.0, 0.01
    return float(row["account_size"] or 10000.0), float(row["risk_pct"] or 0.01)


def _get_user_watchlist(user_id: int) -> list[str]:
    conn = get_db()
    rows = conn.execute(
        "SELECT ticker_symbol FROM watchlists WHERE user_id = %s ORDER BY date_added DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [r["ticker_symbol"] for r in rows]


def _result_to_dict(result) -> dict:
    conditions = [
        {"label": c.label, "passed": c.passed, "value": c.value, "required": c.required}
        for c in result.conditions
    ]
    risk = None
    if result.risk is not None:
        risk = {
            "entry_price": result.risk.entry_price,
            "stop_loss": result.risk.stop_loss,
            "target": getattr(result.risk, "target", None) or getattr(result.risk, "target_1", None),
            "risk_reward": result.risk.risk_reward,
            "atr": result.risk.atr,
            "position_size": result.risk.position_size,
        }
    return {
        "name": result.name,
        "type": result.type,
        "verdict": result.verdict,
        "score": result.score,
        "ticker": getattr(result, "ticker", None),
        "conditions": conditions,
        "risk": risk,
    }


# ── Fixed paths first — must come before /{ticker} ───────────────────────────

@router.get("/settings")
def get_settings(user: dict = Depends(get_current_user)):
    account_size, risk_pct = _get_user_settings(user["id"])
    return {"account_size": account_size, "risk_pct": risk_pct}


@router.patch("/settings")
def update_settings(settings: UserSettings, user: dict = Depends(get_current_user)):
    if settings.account_size <= 0:
        raise HTTPException(status_code=422, detail="account_size must be > 0")
    if not (0 < settings.risk_pct <= 0.05):
        raise HTTPException(status_code=422, detail="risk_pct must be > 0 and <= 0.05")

    conn = get_db()
    conn.execute(
        "UPDATE users SET account_size = %s, risk_pct = %s WHERE id = %s",
        (settings.account_size, settings.risk_pct, user["id"]),
    )
    conn.commit()
    conn.close()
    return {"account_size": settings.account_size, "risk_pct": settings.risk_pct}


@router.get("/scan/watchlist")
def scan_watchlist(user: dict = Depends(get_current_user)):
    tickers = _get_user_watchlist(user["id"])
    if not tickers:
        return []

    account_size, risk_pct = _get_user_settings(user["id"])
    scanner = StrategyScanner()

    def _scan_one(ticker: str) -> list:
        try:
            results = scanner.scan(ticker, account_size, risk_pct)
            for r in results:
                r.ticker = ticker
            return results
        except Exception as e:
            print(f"Scanner skip {ticker}: {e}")
            return []

    all_results = []
    with ThreadPoolExecutor(max_workers=min(len(tickers), 10)) as pool:
        futures = {pool.submit(_scan_one, t): t for t in tickers}
        for future in as_completed(futures):
            all_results.extend(future.result())

    all_results.sort(key=lambda r: r.score, reverse=True)
    return [_result_to_dict(r) for r in all_results]


# ── GET /strategies/{ticker} — path param last ────────────────────────────────

@router.get("/{ticker}")
def get_strategies(ticker: str, user: dict = Depends(get_current_user)):
    symbol = ticker.upper()

    try:
        get_or_refresh_data(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")

    account_size, risk_pct = _get_user_settings(user["id"])

    scanner = StrategyScanner()
    try:
        results = scanner.scan(symbol, account_size, risk_pct)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Scanner error: {e}")

    return [_result_to_dict(r) for r in results]
