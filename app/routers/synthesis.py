from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import ANTHROPIC_API_KEY, OPENAI_API_KEY, SYNTHESIS_PROVIDER
from app.services.ai_engine import stream_narrative
from app.services.market_data import get_or_refresh_data, get_weekly_prices
from app.services.ta_engine import _prepare_dataframe, analyze_ticker

router = APIRouter(prefix="/synthesize", tags=["synthesis"])


@router.get("/{ticker}")
async def synthesize(ticker: str):
    """Stream a copilot narrative for a ticker via SSE."""
    try:
        ticker_info, price_list, _source = get_or_refresh_data(ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        weekly_price_list = get_weekly_prices(ticker.upper())
    except Exception:
        weekly_price_list = []

    try:
        df = _prepare_dataframe(price_list)
        price = float(df["close"].iloc[-1])
        analysis = analyze_ticker(df, ticker_info["symbol"], price, weekly_price_list)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

    analysis["company_name"] = ticker_info.get("company_name")
    analysis["sector"] = ticker_info.get("sector")

    # ── Eagerly validate API key BEFORE creating StreamingResponse ─────────────
    # stream_narrative is an async generator: calling it only creates the object,
    # it executes NO code until iterated. Any validation inside the generator body
    # would fire after the 200 OK header is sent, crashing mid-stream and leaving
    # the client connection in a hanging state. Validate here instead.
    if SYNTHESIS_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is not configured. Set it in the environment and restart.",
        )
    if SYNTHESIS_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured. Set it in the environment and restart.",
        )

    try:
        narrative_gen = stream_narrative(analysis)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    async def _generate():
        try:
            async for chunk in narrative_gen:
                yield f"data: {chunk}\n\n"
        except Exception as e:
            # Yield an error SSE event so the client stream terminates cleanly
            # instead of leaving the connection hanging indefinitely.
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
