from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.services.tinvest_service import tinvest_service
from app.services.token_crypto import decrypt_secret, encrypt_secret, mask_secret

router = APIRouter(prefix="/api/brokers", tags=["brokers"])


@router.get("/connections", response_model=list[schemas.BrokerConnectionRead])
def list_connections(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return crud.list_broker_connections(db, current_user.id)


@router.post("/tinvest/preview", response_model=schemas.BrokerPreview)
async def preview_tinvest_accounts(data: schemas.TInvestTokenPreview):
    accounts = await run_in_threadpool(
        tinvest_service.get_accounts,
        data.token.strip(),
        data.sandbox,
    )
    return schemas.BrokerPreview(provider="tinvest", sandbox=data.sandbox, accounts=accounts)


@router.post(
    "/tinvest/connect",
    response_model=schemas.BrokerConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def connect_tinvest(
    data: schemas.TInvestConnect,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    token = data.token.strip()
    account = await run_in_threadpool(
        tinvest_service.get_account,
        token,
        data.account_id,
        data.sandbox,
    )
    return crud.upsert_broker_connection(
        db,
        current_user.id,
        provider=tinvest_service.provider,
        account_id=account.id,
        account_name=account.name,
        account_type=account.type,
        access_level=account.access_level,
        token_encrypted=encrypt_secret(token),
        token_mask=mask_secret(token),
        sandbox=data.sandbox,
    )


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    connection = crud.get_broker_connection(db, current_user.id, connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подключение не найдено")
    crud.delete_broker_connection(db, connection)


@router.post("/connections/{connection_id}/sync", response_model=schemas.BrokerSyncResult)
async def sync_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    connection = crud.get_broker_connection(db, current_user.id, connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подключение не найдено")

    try:
        token = decrypt_secret(connection.token_encrypted)
        positions = await run_in_threadpool(
            tinvest_service.get_portfolio,
            token,
            connection.account_id,
            connection.sandbox,
        )
    except Exception as exc:
        message = getattr(exc, "detail", None) or str(exc)
        crud.mark_broker_sync_error(db, connection, message)
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    imported = 0
    skipped = 0
    result_positions: list[schemas.BrokerSyncPosition] = []
    existing = {h.ticker: h for h in crud.list_holdings(db, current_user.id)}

    for pos in positions:
        if not pos.ticker or pos.quantity <= 0:
            skipped += 1
            continue

        note = f"T-Invest: {connection.account_name or connection.account_id}"
        if pos.currency and pos.currency != "USD":
            note = f"{note}; валюта {pos.currency}"

        if pos.ticker in existing:
            holding = existing[pos.ticker]
            holding.shares = pos.quantity
            holding.avg_price = Decimal(str(round(float(pos.avg_price), 4)))
            holding.notes = note
        else:
            db.add(
                models.PortfolioHolding(
                    user_id=current_user.id,
                    ticker=pos.ticker,
                    shares=pos.quantity,
                    avg_price=Decimal(str(round(float(pos.avg_price), 4))),
                    notes=note,
                )
            )
        imported += 1
        result_positions.append(
            schemas.BrokerSyncPosition(
                ticker=pos.ticker,
                name=pos.name,
                quantity=float(pos.quantity),
                avg_price=round(float(pos.avg_price), 4),
                currency=pos.currency,
            )
        )

    db.commit()
    crud.mark_broker_sync_success(db, connection)

    return schemas.BrokerSyncResult(
        connection_id=connection.id,
        account_id=connection.account_id,
        imported=imported,
        skipped=skipped,
        positions=result_positions,
        message=f"Синхронизировано позиций: {imported}. Ручные позиции без совпадения не удалялись.",
    )
