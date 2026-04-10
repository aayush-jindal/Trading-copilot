"""
Options opportunity scanner — FastAPI router.

Endpoints:
  POST /options/scan          Run a multi-ticker scan (async, returns JSON)
  GET  /options/scan/{ticker} Run a single-ticker scan
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.options.scanner import run_scan, scan_ticker
from app.services.options.ai_narrative import generate_narrative
from app.services.options.formatter import format_ticker_block

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/options", tags=["options"])


# ── Request / response models ─────────────────────────────────────────────────

class ScanRequest(BaseModel):
    tickers:  List[str]         = Field(..., min_length=1, description="List of ticker symbols")
    settings: Dict[str, Any]    = Field(default_factory=dict, description="Override defaults (e.g. risk_free_rate)")
    include_ai: bool             = Field(default=True, description="Generate AI narrative synthesis")
    include_formatted: bool      = Field(default=False, description="Include terminal-style formatted output per ticker")


class TickerResult(BaseModel):
    ticker:               str
    name:                 Optional[str]       = None
    sector:               Optional[str]       = None
    current_price:        Optional[float]     = None
    opportunities:        List[Dict[str, Any]] = []
    knowledge_strategies: Optional[Any]       = None
    error:                Optional[str]       = None
    formatted:            Optional[str]       = None  # terminal-style block (opt-in)


class ScanResponse(BaseModel):
    results:      List[TickerResult]
    ai_narrative: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scan", response_model=ScanResponse, summary="Scan a watchlist for options opportunities")
def scan_watchlist(body: ScanRequest) -> ScanResponse:
    """
    Run the options scanner for a list of tickers.

    - Fetches market data via TC's DB cache (yfinance refresh if stale).
    - Runs TC's full TA engine for each ticker.
    - Builds multi-leg option opportunities across short/medium/long outlooks.
    - Optionally queries the knowledge base RAG pipeline.
    - Optionally generates an AI narrative synthesis across all results.
    """
    raw = run_scan([t.upper() for t in body.tickers], body.settings)

    results = []
    for r in raw:
        formatted = format_ticker_block(r) if body.include_formatted else None
        results.append(
            TickerResult(
                ticker=r["ticker"],
                name=r.get("name"),
                sector=r.get("sector"),
                current_price=r.get("current_price"),
                opportunities=r.get("opportunities", []),
                knowledge_strategies=r.get("knowledge_strategies"),
                error=r.get("error"),
                formatted=formatted,
            )
        )

    ai_narrative: Optional[str] = None
    if body.include_ai and any(not r.error for r in results):
        try:
            ai_narrative = generate_narrative(raw)
        except Exception as exc:
            logger.error(f"AI narrative generation failed: {exc}")
            ai_narrative = f"[AI narrative error: {exc}]"

    return ScanResponse(results=results, ai_narrative=ai_narrative)


@router.get(
    "/scan/{ticker}",
    response_model=TickerResult,
    summary="Scan a single ticker for options opportunities",
)
def scan_single(
    ticker: str,
    include_formatted: bool = False,
    risk_free_rate: float = 0.045,
) -> TickerResult:
    """
    Run the options scanner for a single ticker symbol.
    """
    try:
        r = scan_ticker(ticker.upper(), settings={"risk_free_rate": risk_free_rate})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    formatted = format_ticker_block(r) if include_formatted else None
    return TickerResult(
        ticker=r["ticker"],
        name=r.get("name"),
        sector=r.get("sector"),
        current_price=r.get("current_price"),
        opportunities=r.get("opportunities", []),
        knowledge_strategies=r.get("knowledge_strategies"),
        error=r.get("error"),
        formatted=formatted,
    )
