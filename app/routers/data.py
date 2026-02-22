from fastapi import APIRouter, HTTPException, Query

from app.models import PriceHistoryResponse
from app.services.market_data import get_latest_prices, get_or_refresh_data

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/{ticker}", response_model=PriceHistoryResponse)
def get_ticker_data(ticker: str):
    try:
        ticker_info, prices, source = get_or_refresh_data(ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return PriceHistoryResponse(
        ticker=ticker_info, prices=prices, count=len(prices), source=source
    )


@router.get("/{ticker}/latest", response_model=PriceHistoryResponse)
def get_ticker_latest(ticker: str, days: int = Query(default=365, ge=1, le=2190)):
    try:
        ticker_info, prices, source = get_latest_prices(ticker, days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return PriceHistoryResponse(
        ticker=ticker_info, prices=prices, count=len(prices), source=source
    )
