from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.ai_analysis import ai_analysis_service
from app.services.dividend_service import get_portfolio_dividends
from app.services.fx_service import get_usd_rub_rate
from app.services.portfolio_analytics import compute_benchmark, compute_risks
from app.services.portfolio_summary import build_daily_summary
from app.services.portfolio_valuation import enrich_holdings
from app.services.stock_service import fetch_quotes

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=list[schemas.PortfolioHoldingRead])
def list_portfolio(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.list_holdings(db, current_user.id)


@router.post("", response_model=schemas.PortfolioHoldingRead, status_code=status.HTTP_201_CREATED)
def add_holding(
    data: schemas.PortfolioHoldingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = crud.get_holding_by_ticker(db, current_user.id, data.ticker)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticker {data.ticker} already in portfolio",
        )
    return crud.create_holding(db, current_user.id, data)


@router.patch("/{holding_id}", response_model=schemas.PortfolioHoldingRead)
def update_holding(
    holding_id: int,
    data: schemas.PortfolioHoldingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    holding = crud.get_holding(db, current_user.id, holding_id)
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return crud.update_holding(db, holding, data)


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(
    holding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    holding = crud.get_holding(db, current_user.id, holding_id)
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    crud.delete_holding(db, holding)


@router.post("/ai-analysis", response_model=schemas.PortfolioAnalysis)
async def portfolio_ai_analysis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await run_in_threadpool(ai_analysis_service.analyze_portfolio, db, current_user.id)


@router.get("/dividends", response_model=schemas.PortfolioDividends)
def portfolio_dividends(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_portfolio_dividends(db, current_user.id)


@router.get("/daily-summary", response_model=schemas.PortfolioDailySummary)
def portfolio_daily_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return build_daily_summary(db, current_user.id)


@router.get("/dashboard", response_model=schemas.DashboardStats)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    holdings = crud.list_holdings(db, current_user.id)
    if not holdings:
        return schemas.DashboardStats(
            holdings_count=0,
            total_cost=0,
            total_value=0,
            total_pnl=0,
            total_pnl_percent=0,
            usd_rub_rate=0,
            total_value_rub=0,
            total_cost_rub=0,
            top_holdings=[],
            chart_holdings=[],
        )

    tickers = [h.ticker for h in holdings]
    quotes = fetch_quotes(tickers)
    enriched, total_cost, total_value, total_pnl, total_cost_rub, total_value_rub = enrich_holdings(
        holdings, quotes
    )
    total_pnl_percent = (total_pnl / total_cost * 100) if total_cost else 0

    return schemas.DashboardStats(
        holdings_count=len(holdings),
        total_cost=total_cost,
        total_value=total_value,
        total_pnl=total_pnl,
        total_pnl_percent=round(total_pnl_percent, 2),
        usd_rub_rate=round(get_usd_rub_rate(), 4),
        total_value_rub=total_value_rub,
        total_cost_rub=total_cost_rub,
        top_holdings=enriched[:5],
        chart_holdings=enriched,
    )


@router.get("/benchmark", response_model=schemas.PortfolioBenchmark)
async def portfolio_benchmark(
    benchmark: str = "SPY",
    range: str = "3mo",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await run_in_threadpool(compute_benchmark, db, current_user.id, benchmark, range)


@router.get("/risks", response_model=schemas.PortfolioRisks)
async def portfolio_risks(
    range: str = "3mo",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await run_in_threadpool(compute_risks, db, current_user.id, range)
