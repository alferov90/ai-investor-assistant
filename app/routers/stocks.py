import logging

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.ai_analysis import ai_analysis_service
from app.services.stock_service import stock_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/{ticker}", response_model=schemas.StockDetail)
async def get_stock(
    ticker: str,
    _: User = Depends(get_current_user),
):
    logger.info("GET stock %s", ticker.upper())
    return await run_in_threadpool(stock_service.get_stock, ticker)


@router.get("/{ticker}/quote", response_model=schemas.StockQuote)
async def get_quote(
    ticker: str,
    _: User = Depends(get_current_user),
):
    logger.info("GET quote %s", ticker.upper())
    return await run_in_threadpool(stock_service.get_quote, ticker)


@router.get("/{ticker}/analysis", response_model=schemas.StockAnalysis)
async def get_analysis(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info("GET analysis %s", ticker.upper())
    result = await run_in_threadpool(ai_analysis_service.analyze, ticker)
    crud.save_analysis(db, current_user.id, result)
    return result
