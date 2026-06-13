from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import User
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
            top_holdings=[],
        )

    tickers = [h.ticker for h in holdings]
    quotes = fetch_quotes(tickers)
    prices = {t: q.price for t, q in quotes.items()}

    total_cost, total_value = crud.portfolio_totals(holdings, prices)
    total_pnl = total_value - total_cost
    total_pnl_percent = (total_pnl / total_cost * 100) if total_cost else 0

    enriched = []
    for holding in holdings:
        shares = float(holding.shares)
        avg_price = float(holding.avg_price)
        price = prices.get(holding.ticker, avg_price)
        value = shares * price
        cost = shares * avg_price
        pnl = value - cost
        enriched.append(
            {
                "ticker": holding.ticker,
                "name": quotes[holding.ticker].name if holding.ticker in quotes else holding.ticker,
                "shares": shares,
                "price": price,
                "value": round(value, 2),
                "pnl": round(pnl, 2),
                "pnl_percent": round((pnl / cost * 100) if cost else 0, 2),
            }
        )

    enriched.sort(key=lambda x: x["value"], reverse=True)

    return schemas.DashboardStats(
        holdings_count=len(holdings),
        total_cost=round(total_cost, 2),
        total_value=round(total_value, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_percent=round(total_pnl_percent, 2),
        top_holdings=enriched[:5],
    )
