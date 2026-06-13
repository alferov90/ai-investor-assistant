from fastapi import APIRouter, Depends

from app import schemas
from app.auth import get_current_user
from app.models import User
from app.services.ai_analysis import analyze_stock
from app.services.stock_service import fetch_stock_quote

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/{ticker}/quote", response_model=schemas.StockQuote)
def get_quote(
    ticker: str,
    _: User = Depends(get_current_user),
):
    return fetch_stock_quote(ticker)


@router.get("/{ticker}/analysis", response_model=schemas.StockAnalysis)
def get_analysis(
    ticker: str,
    _: User = Depends(get_current_user),
):
    quote = fetch_stock_quote(ticker)
    return analyze_stock(quote)
