"""USD/RUB and currency conversion helpers."""

from __future__ import annotations

import logging

import httpx

from app.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

_RATES: dict[str, float] = {"USD": 1.0, "RUB": 0.0}


def get_usd_rub_rate() -> float:
    cached = cache_get("fx:usd_rub")
    if cached:
        return float(cached)

    rate = _fetch_cbr_usd_rub()
    if rate is None:
        rate = _fetch_moex_usd_rub()
    if rate is None or rate <= 0:
        rate = 90.0
        logger.warning("Using fallback USD/RUB rate %.2f", rate)

    cache_set("fx:usd_rub", rate, 1800)
    _RATES["RUB"] = rate
    return rate


def _fetch_cbr_usd_rub() -> float | None:
    try:
        response = httpx.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=8)
        response.raise_for_status()
        val = response.json().get("Valute", {}).get("USD", {}).get("Value")
        return float(val) if val else None
    except Exception as exc:
        logger.warning("CBR USD/RUB failed: %s", exc)
        return None


def _fetch_moex_usd_rub() -> float | None:
    try:
        url = (
            "https://iss.moex.com/iss/engines/currency/markets/selt/"
            "boards/CETS/securities/USD000UTSTOM.json"
        )
        response = httpx.get(url, params={"iss.meta": "off", "iss.only": "marketdata"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        md = payload.get("marketdata") or {}
        cols = md.get("columns") or []
        rows = md.get("data") or []
        if not rows:
            return None
        row = dict(zip(cols, rows[0]))
        return float(row.get("LAST") or row.get("MARKETPRICE") or 0) or None
    except Exception as exc:
        logger.warning("MOEX USD/RUB failed: %s", exc)
        return None


def to_usd(amount: float, currency: str) -> float:
    currency = (currency or "USD").upper()
    if currency == "USD":
        return amount
    if currency == "RUB":
        rate = get_usd_rub_rate()
        return amount / rate if rate else amount
    return amount


def to_rub(amount: float, currency: str) -> float:
    currency = (currency or "USD").upper()
    if currency == "RUB":
        return amount
    if currency == "USD":
        return amount * get_usd_rub_rate()
    return amount
