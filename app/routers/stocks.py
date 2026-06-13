from fastapi import APIRouter, Depends

from app import schemas
from app.auth import get_current_user
from app.models import User
from app.services.ai_analysis import analyze_stock
from app.services.stock_service import stock_service

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/{ticker}", response_model=schemas.StockDetail)
def get_stock(
    ticker: str,
    _: User = Depends(get_current_user),
):
    return stock_service.get_stock(ticker)


@router.get("/{ticker}/quote", response_model=schemas.StockQuote)
def get_quote(
    ticker: str,
    _: User = Depends(get_current_user),
):
    return stock_service.get_quote(ticker)


@router.get("/{ticker}/analysis", response_model=schemas.StockAnalysis)
def get_analysis(
    ticker: str,
    _: User = Depends(get_current_user),
):
    quote = stock_service.get_quote(ticker)
    return analyze_stock(quote)
