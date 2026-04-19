"""Technical analysis and RAG strategy endpoints.

GET /analyze/{ticker}                    — full TA signal set for a ticker
GET /analyze/{ticker}/knowledge-strategies — RAG pipeline: signals → book
                                             retrieval → Claude → strategies
"""

from datetime import date

import psycopg2.extras
from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.models import AnalysisResponse
from app.services.market_data import get_or_refresh_data, get_or_refresh_hourly_data, get_weekly_prices
from app.services.ta_engine import _prepare_dataframe, analyze_ticker

router = APIRouter(prefix="/analyze", tags=["analysis"])


@router.get("/{ticker}", response_model=AnalysisResponse)
def analyze(ticker: str):
    """Run full technical analysis on a ticker."""
    try:
        ticker_info, price_list, source = get_or_refresh_data(ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    try:
        weekly_price_list = get_weekly_prices(ticker.upper())
    except Exception:
        weekly_price_list = []

    # Hourly data is best-effort — failure must not block daily analysis
    try:
        hourly_df = get_or_refresh_hourly_data(ticker.upper())
    except Exception:
        hourly_df = None

    try:
        df = _prepare_dataframe(price_list)
        price = df["close"].iloc[-1]
        result = analyze_ticker(
            df,
            ticker_info["symbol"],
            float(price),
            weekly_price_list,
            hourly_df=hourly_df,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

    return result


@router.get("/{ticker}/knowledge-strategies")
def knowledge_strategies(ticker: str):
    """RAG pipeline: live signals → book retrieval → Claude → grounded strategies.

    Results are cached per (ticker, calendar date). On a cache hit the Claude
    call is skipped and the cached dict is returned immediately.
    """
    symbol = ticker.upper()
    today = date.today()

    # ── Cache read ────────────────────────────────────────────────────────────
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT result FROM knowledge_strategy_cache WHERE ticker = %s AND cache_date = %s",
            (symbol, today),
        ).fetchone()
    finally:
        conn.close()

    if row:
        return {"ticker": symbol, "strategies": row["result"]}

    # ── Generate via Claude ───────────────────────────────────────────────────
    try:
        from tools.knowledge_base.strategy_gen import generate_strategies  # lazy import
        result = generate_strategies(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # ── Cache write ───────────────────────────────────────────────────────────
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO knowledge_strategy_cache (ticker, cache_date, result)
               VALUES (%s, %s, %s)
               ON CONFLICT (ticker, cache_date) DO NOTHING""",
            (symbol, today, psycopg2.extras.Json(result)),
        )
        conn.commit()
    except Exception:
        pass  # Cache write failure must not break the response
    finally:
        conn.close()

    return {"ticker": symbol, "strategies": result}
