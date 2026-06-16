from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.stock_service import stock_service

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[schemas.WatchlistRead])
async def list_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = crud.list_watchlist(db, current_user.id)
    if not items:
        return []

    tickers = [i.ticker for i in items]
    quotes = await run_in_threadpool(stock_service.get_quotes, tickers)

    result = []
    for item in items:
        q = quotes.get(item.ticker)
        result.append(
            schemas.WatchlistRead(
                id=item.id,
                ticker=item.ticker,
                notes=item.notes,
                created_at=item.created_at,
                current_price=q.price if q else None,
                change_percent=q.change_percent if q else None,
                currency=q.currency if q else "USD",
                market=q.market if q else "us",
            )
        )
    return result


@router.post("", response_model=schemas.WatchlistRead, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(
    data: schemas.WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        db.query(models.WatchlistItem)
        .filter(
            models.WatchlistItem.user_id == current_user.id,
            models.WatchlistItem.ticker == data.ticker,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"{data.ticker} already in watchlist")
    item = crud.create_watchlist_item(db, current_user.id, data)
    return schemas.WatchlistRead.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = crud.get_watchlist_item(db, current_user.id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    crud.delete_watchlist_item(db, item)
