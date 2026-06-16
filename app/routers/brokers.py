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


def _confirmation_text(direction: str, ticker: str, lots: int) -> str:
    return f"{direction.upper()} {ticker.upper()} {lots}"


def _money_to_float(value: dict | None) -> float:
    if not value:
        return 0.0
    units = Decimal(str(value.get("units") or 0))
    nano = Decimal(str(value.get("nano") or 0)) / Decimal("1000000000")
    return round(float(units + nano), 4)


def _order_status(data: dict) -> str:
    return data.get("executionReportStatus") or data.get("execution_report_status") or ""


async def _order_preview(
    data: schemas.BrokerOrderPreviewRequest,
    db: Session,
    current_user: models.User,
) -> tuple[models.BrokerConnection, str, schemas.BrokerOrderPreview]:
    connection = crud.get_broker_connection(db, current_user.id, data.connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подключение не найдено")

    token = decrypt_secret(connection.token_encrypted)
    instrument = await run_in_threadpool(
        tinvest_service.find_instrument,
        token,
        data.ticker,
        connection.sandbox,
    )
    estimated_amount = float(data.limit_price) * data.lots * instrument.lot
    warnings = [
        "Отправляется только лимитная заявка. Исполнение не гарантировано.",
        "Количество указывается в лотах, не в штуках.",
    ]
    if not connection.sandbox:
        warnings.append("Это реальный брокерский счет. Заявка может быть отправлена на биржу.")
    if "read" in (connection.access_level or "").lower():
        warnings.append("Подключение похоже на read-only: T-Invest отклонит торговую заявку.")

    preview = schemas.BrokerOrderPreview(
        connection_id=connection.id,
        account_id=connection.account_id,
        sandbox=connection.sandbox,
        instrument=schemas.BrokerInstrumentPreview(
            ticker=instrument.ticker,
            name=instrument.name,
            instrument_id=instrument.instrument_id,
            currency=instrument.currency,
            lot=instrument.lot,
            exchange=instrument.exchange,
            trading_status=instrument.trading_status,
        ),
        direction=data.direction,
        lots=data.lots,
        limit_price=float(data.limit_price),
        estimated_amount=round(estimated_amount, 4),
        currency=instrument.currency,
        confirm_text=_confirmation_text(data.direction, instrument.ticker, data.lots),
        warnings=warnings,
    )
    return connection, token, preview


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


@router.get("/orders", response_model=list[schemas.BrokerOrderRead])
def list_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return crud.list_broker_orders(db, current_user.id)


@router.post("/orders/preview", response_model=schemas.BrokerOrderPreview)
async def preview_order(
    data: schemas.BrokerOrderPreviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _, _, preview = await _order_preview(data, db, current_user)
    return preview


@router.post("/orders/place", response_model=schemas.BrokerOrderPlaceResult)
async def place_order(
    data: schemas.BrokerOrderPlaceRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    connection, token, preview = await _order_preview(data, db, current_user)
    expected = preview.confirm_text
    if data.confirm_text.strip().upper() != expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Для отправки заявки введите подтверждение: {expected}",
        )

    request_id, response = await run_in_threadpool(
        tinvest_service.place_limit_order,
        token,
        account_id=connection.account_id,
        instrument_id=preview.instrument.instrument_id,
        direction=data.direction,
        lots=data.lots,
        limit_price=data.limit_price,
        sandbox=connection.sandbox,
    )
    provider_order_id = response.get("orderId") or response.get("order_id") or request_id
    lots_executed = int(response.get("lotsExecuted") or response.get("lots_executed") or 0)
    order = crud.create_broker_order(
        db,
        current_user.id,
        connection,
        order_id=provider_order_id,
        request_id=request_id,
        ticker=preview.instrument.ticker,
        instrument_id=preview.instrument.instrument_id,
        direction=data.direction,
        lots_requested=data.lots,
        lots_executed=lots_executed,
        limit_price=data.limit_price,
        currency=preview.currency,
        status=_order_status(response),
        message=response.get("message") or "",
    )

    return schemas.BrokerOrderPlaceResult(
        order=order,
        provider_response=response,
        message="Лимитная заявка отправлена в T-Invest.",
    )


@router.get("/connections/{connection_id}/active-orders")
async def list_active_orders(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    connection = crud.get_broker_connection(db, current_user.id, connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подключение не найдено")
    token = decrypt_secret(connection.token_encrypted)
    return await run_in_threadpool(
        tinvest_service.list_active_orders,
        token,
        connection.account_id,
        connection.sandbox,
    )


@router.post("/orders/{order_pk}/cancel", response_model=schemas.BrokerOrderRead)
async def cancel_order(
    order_pk: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = crud.get_broker_order(db, current_user.id, order_pk)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    connection = crud.get_broker_connection(db, current_user.id, order.connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подключение не найдено")
    token = decrypt_secret(connection.token_encrypted)
    await run_in_threadpool(
        tinvest_service.cancel_order,
        token,
        connection.account_id,
        order.order_id,
        connection.sandbox,
    )
    return crud.update_broker_order_status(
        db,
        order,
        status="EXECUTION_REPORT_STATUS_CANCELLED",
        message="Отмена отправлена в T-Invest.",
    )
