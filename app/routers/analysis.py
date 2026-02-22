from fastapi import APIRouter, HTTPException

from app.models import AnalysisResponse
from app.services.market_data import get_or_refresh_data
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
        df = _prepare_dataframe(price_list)
        price = df["close"].iloc[-1]
        result = analyze_ticker(df, ticker_info["symbol"], float(price))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

    return result
