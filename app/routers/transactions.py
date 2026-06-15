from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.holdings_sync import compute_transaction_summary, rebuild_holdings_from_transactions
from app.services.transaction_import import parse_csv, sample_csv

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[schemas.TransactionRead])
def list_transactions(
    ticker: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.list_transactions(db, current_user.id, ticker=ticker)


@router.get("/summary", response_model=schemas.TransactionSummary)
def transaction_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = compute_transaction_summary(db, current_user.id)
    return schemas.TransactionSummary(**data)


@router.get("/sample.csv", response_class=PlainTextResponse)
def download_sample_csv():
    return PlainTextResponse(sample_csv(), media_type="text/csv")


@router.post("", response_model=schemas.TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: schemas.TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn = crud.create_transaction(db, current_user.id, data)
    await run_in_threadpool(rebuild_holdings_from_transactions, db, current_user.id)
    return txn


@router.post("/import", response_model=schemas.TransactionImportResult)
async def import_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    rows, errors = parse_csv(content)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=errors[0] if errors else "No valid rows in CSV",
        )

    crud.create_transactions_bulk(db, current_user.id, rows, source="csv")
    rebuild = await run_in_threadpool(rebuild_holdings_from_transactions, db, current_user.id)

    return schemas.TransactionImportResult(
        imported=len(rows),
        skipped=len(errors),
        errors=errors[:20],
        holdings_updated=rebuild.holdings_count,
        realized_pnl=round(rebuild.realized_pnl, 2),
        dividends_total=round(rebuild.dividends_total, 2),
    )


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn = crud.get_transaction(db, current_user.id, txn_id)
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    crud.delete_transaction(db, txn)
    await run_in_threadpool(rebuild_holdings_from_transactions, db, current_user.id)
