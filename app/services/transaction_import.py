"""Parse broker CSV exports into transaction rows."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.schemas import TransactionCreate

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M:%S",
)

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "datetime", "trade date", "time", "дата", "operation date"),
    "ticker": ("ticker", "symbol", "instrument", "тикер", "figi"),
    "type": ("type", "side", "operation", "action", "тип", "операция"),
    "shares": ("shares", "quantity", "qty", "amount", "количество", "кол-во"),
    "price": ("price", "cost", "t. price", "trade price", "цена", "avg price"),
    "fee": ("fee", "commission", "comm", "комиссия", "comm/fee"),
    "notes": ("notes", "comment", "description", "заметки"),
}

_BUY_WORDS = frozenset({"buy", "b", "purchase", "покупка", "купля", "bot"})
_SELL_WORDS = frozenset({"sell", "s", "sale", "продажа", "sold"})
_DIV_WORDS = frozenset({"dividend", "div", "дивиденд", "дивиденды"})


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _map_headers(row: list[str]) -> dict[str, int]:
    normalized = [_normalize_header(c) for c in row]
    mapping: dict[str, int] = {}
    for field, aliases in _COLUMN_ALIASES.items():
        for idx, col in enumerate(normalized):
            if col in aliases or any(a in col for a in aliases):
                mapping[field] = idx
                break
    return mapping


def _parse_date(raw: str) -> datetime:
    text = raw.strip()
    if not text:
        raise ValueError("empty date")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {raw}")


def _parse_decimal(raw: str) -> Decimal:
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned or cleaned in {".", "-", "-."}:
        return Decimal("0")
    return Decimal(cleaned)


def _parse_type(raw: str) -> str:
    val = raw.strip().lower()
    if val in _BUY_WORDS or "buy" in val or "покуп" in val:
        return "buy"
    if val in _SELL_WORDS or "sell" in val or "продаж" in val:
        return "sell"
    if val in _DIV_WORDS or "dividend" in val or "дивид" in val:
        return "dividend"
    raise ValueError(f"unknown transaction type: {raw}")


def _parse_row(mapping: dict[str, int], row: list[str], line_no: int) -> TransactionCreate:
    def cell(field: str, default: str = "") -> str:
        idx = mapping.get(field)
        if idx is None or idx >= len(row):
            return default
        return row[idx].strip()

    ticker = cell("ticker").upper().replace(".US", "").replace("/", "")
    if not ticker or ticker in {"SYMBOL", "TICKER"}:
        raise ValueError("missing ticker")

    txn_type = _parse_type(cell("type") or "buy")
    traded_at = _parse_date(cell("date"))
    shares = _parse_decimal(cell("shares") or "0")
    price = _parse_decimal(cell("price") or "0")
    fee = _parse_decimal(cell("fee") or "0")
    notes = cell("notes")

    if txn_type == "dividend":
        if price <= 0 and shares > 0:
            price = shares
        shares = Decimal("0")
    else:
        if shares <= 0:
            raise ValueError("shares must be positive")
        if price <= 0:
            raise ValueError("price must be positive")

    return TransactionCreate(
        ticker=ticker,
        txn_type=txn_type,
        shares=shares,
        price=price,
        fee=fee,
        traded_at=traded_at,
        notes=notes,
    )


def parse_csv(content: str) -> tuple[list[TransactionCreate], list[str]]:
    text = content.strip()
    if not text:
        return [], ["Файл пуст"]

    delimiter = ";" if text.count(";") > text.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        return [], ["Нужна строка заголовков и хотя бы одна сделка"]

    mapping = _map_headers(rows[0])
    if "ticker" not in mapping:
        return [], ["Не найдена колонка ticker/symbol"]
    if "date" not in mapping:
        return [], ["Не найдена колонка date"]

    parsed: list[TransactionCreate] = []
    errors: list[str] = []

    for line_no, row in enumerate(rows[1:], start=2):
        if not row or all(not c.strip() for c in row):
            continue
        try:
            parsed.append(_parse_row(mapping, row, line_no))
        except Exception as exc:
            errors.append(f"Строка {line_no}: {exc}")

    return parsed, errors


def sample_csv() -> str:
    return (
        "date,ticker,type,shares,price,fee,notes\n"
        "2025-01-15,AAPL,buy,10,185.50,1.00,Открытие позиции\n"
        "2025-03-20,NVDA,buy,5,875.00,1.00,\n"
        "2025-06-01,AAPL,sell,3,210.00,1.00,Частичная фиксация\n"
    )
