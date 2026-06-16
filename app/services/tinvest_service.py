"""Read-only T-Invest integration through the official REST gateway."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import json
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from app import schemas

_PROD_REST = "https://invest-public-api.tinkoff.ru/rest"
_SANDBOX_REST = "https://sandbox-invest-public-api.tinkoff.ru/rest"
_CONTRACT = "tinkoff.public.invest.api.contract.v1"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


@dataclass
class TInvestPosition:
    ticker: str
    name: str
    quantity: Decimal
    avg_price: Decimal
    currency: str


@dataclass
class TInvestInstrument:
    ticker: str
    name: str
    instrument_id: str
    currency: str
    lot: int
    exchange: str = ""
    trading_status: str = ""


def _decimal_from_api(value: dict | None) -> Decimal:
    if not value:
        return Decimal("0")
    units = Decimal(str(value.get("units") or 0))
    nano = Decimal(str(value.get("nano") or 0)) / Decimal("1000000000")
    return units + nano


def _quotation_from_decimal(value: Decimal) -> dict:
    quantized = value.quantize(Decimal("0.000000001"))
    units = int(quantized)
    nano = int((quantized - Decimal(units)) * Decimal("1000000000"))
    return {"units": str(units), "nano": nano}


def _friendly_error(exc: Exception) -> HTTPException:
    text = str(exc)
    detail = "Не удалось подключиться к T-Invest. Проверьте токен и доступ к счету."
    try:
        payload = json.loads(text[text.index("{"):])
        message = payload.get("message") or payload.get("description")
        if message:
            detail = f"T-Invest: {message}"
    except (ValueError, json.JSONDecodeError):
        pass

    if "40003" in text or "Authentication token" in text or "401" in text:
        detail = "T-Invest отклонил токен. Проверьте, что токен актуален и скопирован полностью."
    elif "403" in text or "PermissionDenied" in text or "permission" in text.lower():
        detail = "T-Invest отказал в доступе. Проверьте права токена и выбранный счет."
    elif "sandbox" in text.lower():
        detail = "Похоже, тип токена не совпадает с режимом Sandbox."
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class TInvestService:
    provider = "tinvest"

    def _base_url(self, sandbox: bool = False) -> str:
        return _SANDBOX_REST if sandbox else _PROD_REST

    def _call(self, token: str, service: str, method: str, payload: dict, sandbox: bool) -> dict:
        url = f"{self._base_url(sandbox)}/{_CONTRACT}.{service}/{method}"
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            raise _friendly_error(Exception(f"{exc.response.status_code}: {body}")) from exc
        except Exception as exc:
            raise _friendly_error(exc) from exc

    def get_accounts(self, token: str, sandbox: bool = False) -> list[schemas.BrokerAccount]:
        data = self._call(token, "UsersService", "GetAccounts", {}, sandbox)
        accounts: list[schemas.BrokerAccount] = []
        for account in data.get("accounts", []):
            opened_at = None
            if account.get("openedDate"):
                try:
                    opened_at = datetime.fromisoformat(account["openedDate"].replace("Z", "+00:00"))
                except ValueError:
                    opened_at = None
            accounts.append(
                schemas.BrokerAccount(
                    id=account.get("id", ""),
                    name=account.get("name") or account.get("id", ""),
                    type=account.get("type", ""),
                    status=account.get("status", ""),
                    access_level=account.get("accessLevel", ""),
                    opened_at=opened_at,
                )
            )
        return accounts

    def get_account(
        self, token: str, account_id: str, sandbox: bool = False
    ) -> schemas.BrokerAccount:
        accounts = self.get_accounts(token, sandbox)
        for account in accounts:
            if account.id == account_id:
                return account
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Счет не найден в списке доступных счетов T-Invest.",
        )

    def _instrument(self, token: str, sandbox: bool, id_type: str, instrument_id: str) -> dict:
        data = self._call(
            token,
            "InstrumentsService",
            "GetInstrumentBy",
            {"idType": id_type, "id": instrument_id},
            sandbox,
        )
        return data.get("instrument", {})

    def _instrument_by_ticker(
        self, token: str, sandbox: bool, ticker: str, class_code: str
    ) -> dict:
        data = self._call(
            token,
            "InstrumentsService",
            "GetInstrumentBy",
            {
                "idType": "INSTRUMENT_ID_TYPE_TICKER",
                "classCode": class_code,
                "id": ticker,
            },
            sandbox,
        )
        return data.get("instrument", {})

    def _resolve_instrument(self, token: str, sandbox: bool, position: dict) -> tuple[str, str, str]:
        figi = position.get("figi") or ""
        uid = position.get("instrumentUid") or ""
        ticker = figi or uid
        name = ticker
        currency = (position.get("averagePositionPrice") or {}).get("currency") or "rub"

        for id_type, instrument_id in (
            ("INSTRUMENT_ID_TYPE_UID", uid),
            ("INSTRUMENT_ID_TYPE_FIGI", figi),
        ):
            if not instrument_id:
                continue
            try:
                instrument = self._instrument(token, sandbox, id_type, instrument_id)
            except Exception:
                continue
            ticker = instrument.get("ticker") or ticker
            name = instrument.get("name") or name
            currency = instrument.get("currency") or currency
            break

        return ticker.upper(), name, currency.upper()

    def find_instrument(self, token: str, ticker: str, sandbox: bool = False) -> TInvestInstrument:
        ticker = ticker.strip().upper()
        candidates = []
        try:
            data = self._call(
                token,
                "InstrumentsService",
                "FindInstrument",
                {"query": ticker, "apiTradeAvailableFlag": True},
                sandbox,
            )
            candidates = data.get("instruments", [])
        except HTTPException:
            candidates = []
        exact = [
            item for item in candidates
            if (item.get("ticker") or "").upper() == ticker and (item.get("uid") or item.get("instrumentUid"))
        ]
        pool = exact or [item for item in candidates if item.get("uid") or item.get("instrumentUid")]
        if pool:
            item = pool[0]
        else:
            item = {}
            for class_code in ("TQBR", "SPBXM", "SPBDE", "TQTF", "TQOB"):
                try:
                    item = self._instrument_by_ticker(token, sandbox, ticker, class_code)
                except HTTPException:
                    continue
                if item:
                    break

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"T-Invest не нашел инструмент {ticker}.",
            )

        return TInvestInstrument(
            ticker=(item.get("ticker") or ticker).upper(),
            name=item.get("name") or ticker,
            instrument_id=item.get("uid") or item.get("instrumentUid") or item.get("figi") or "",
            currency=(item.get("currency") or "rub").upper(),
            lot=int(item.get("lot") or 1),
            exchange=item.get("exchange") or "",
            trading_status=item.get("tradingStatus") or "",
        )

    def get_portfolio(
        self, token: str, account_id: str, sandbox: bool = False
    ) -> list[TInvestPosition]:
        data = self._call(
            token,
            "OperationsService",
            "GetPortfolio",
            {"accountId": account_id},
            sandbox,
        )
        positions: list[TInvestPosition] = []
        for item in data.get("positions", []):
            quantity = _decimal_from_api(item.get("quantity"))
            if quantity <= 0:
                continue

            instrument_type = (item.get("instrumentType") or "").lower()
            if instrument_type and instrument_type not in {"share", "bond", "etf", "currency"}:
                continue

            ticker, name, currency = self._resolve_instrument(token, sandbox, item)
            avg_price = _decimal_from_api(item.get("averagePositionPrice"))
            if avg_price <= 0:
                avg_price = _decimal_from_api(item.get("currentPrice"))

            positions.append(
                TInvestPosition(
                    ticker=ticker,
                    name=name,
                    quantity=quantity,
                    avg_price=avg_price,
                    currency=currency,
                )
            )

        return positions

    def place_limit_order(
        self,
        token: str,
        *,
        account_id: str,
        instrument_id: str,
        direction: str,
        lots: int,
        limit_price: Decimal,
        sandbox: bool = False,
    ) -> tuple[str, dict]:
        request_id = str(uuid4())
        payload = {
            "quantity": str(lots),
            "price": _quotation_from_decimal(limit_price),
            "direction": "ORDER_DIRECTION_BUY" if direction == "buy" else "ORDER_DIRECTION_SELL",
            "accountId": account_id,
            "orderType": "ORDER_TYPE_LIMIT",
            "orderId": request_id,
            "instrumentId": instrument_id,
        }
        data = self._call(token, "OrdersService", "PostOrder", payload, sandbox)
        return request_id, data

    def list_active_orders(self, token: str, account_id: str, sandbox: bool = False) -> list[dict]:
        data = self._call(
            token,
            "OrdersService",
            "GetOrders",
            {"accountId": account_id},
            sandbox,
        )
        return data.get("orders", [])

    def cancel_order(
        self, token: str, account_id: str, order_id: str, sandbox: bool = False
    ) -> dict:
        return self._call(
            token,
            "OrdersService",
            "CancelOrder",
            {"accountId": account_id, "orderId": order_id},
            sandbox,
        )


tinvest_service = TInvestService()
