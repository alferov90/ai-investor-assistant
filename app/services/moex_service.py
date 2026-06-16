"""MOEX ISS API: quotes, history, dividends."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

_ISS_BASE = "https://iss.moex.com/iss"
_BOARD = "TQBR"
_TIMEOUT = 12

_KNOWN_MOEX = frozenset({
    "SBER", "GAZP", "LKOH", "YNDX", "ROSN", "NVTK", "GMKN", "TCSG", "T", "MGNT",
    "PLZL", "MTSS", "ALRS", "CHMF", "NLMK", "SNGS", "TATN", "VTBR", "MOEX", "PHOR",
    "IRAO", "FEES", "HYDR", "RTKM", "AFKS", "PIKK", "AFLT", "VKCO", "OZON", "HEAD",
    "X5", "BSPB", "CBOM", "MAGN", "RUAL", "SGZH", "FLOT", "SMLT", "LSRG", "TRNFP",
})

_HISTORY_DAYS = {"1mo": 32, "3mo": 96, "6mo": 192, "1y": 370}


def normalize_moex_ticker(symbol: str) -> tuple[str, bool]:
    raw = symbol.strip().upper()
    if raw.startswith("MOEX:"):
        return raw[5:], True
    if raw.endswith(".ME"):
        return raw[:-3], True
    if raw in _KNOWN_MOEX:
        return raw, True
    return raw, False


def is_moex_ticker(symbol: str) -> bool:
    ticker, explicit = normalize_moex_ticker(symbol)
    if explicit:
        return True
    if not re.fullmatch(r"[A-Z]{2,10}", ticker):
        return False
    if ticker in _KNOWN_MOEX:
        return True
    return _moex_exists(ticker)


def _moex_exists(ticker: str) -> bool:
    cache_key = f"moex:exists:{ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        return bool(cached)

    try:
        payload = _iss_get(
            f"/engines/stock/markets/shares/boards/{_BOARD}/securities/{ticker}.json",
            {"iss.meta": "off", "iss.only": "securities"},
        )
        rows = (payload.get("securities") or {}).get("data") or []
        exists = len(rows) > 0
        cache_set(cache_key, int(exists), 86400)
        return exists
    except Exception:
        return False


def _iss_get(path: str, params: dict | None = None) -> dict[str, Any]:
    response = httpx.get(f"{_ISS_BASE}{path}", params=params or {}, timeout=_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _table(payload: dict, key: str) -> list[dict[str, Any]]:
    block = payload.get(key) or {}
    cols = block.get("columns") or []
    rows = block.get("data") or []
    return [dict(zip(cols, row)) for row in rows]


def fetch_moex_quote(ticker: str) -> dict[str, Any]:
    ticker = normalize_moex_ticker(ticker)[0]
    cache_key = f"moex:quote:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    payload = _iss_get(
        f"/engines/stock/markets/shares/boards/{_BOARD}/securities/{ticker}.json",
        {"iss.meta": "off", "iss.only": "marketdata,securities"},
    )
    md_rows = _table(payload, "marketdata")
    sec_rows = _table(payload, "securities")
    if not md_rows and not sec_rows:
        raise ValueError(f"MOEX security not found: {ticker}")

    md = md_rows[0] if md_rows else {}
    sec = sec_rows[0] if sec_rows else {}
    current = _num(md.get("LAST") or md.get("MARKETPRICE") or sec.get("PREVPRICE"))
    if current is None:
        raise ValueError(f"No MOEX price for {ticker}")

    previous = _num(sec.get("PREVPRICE") or md.get("LASTTOPREVPRICE")) or current
    name = str(sec.get("SHORTNAME") or sec.get("SECNAME") or ticker)

    info = {
        "regularMarketPrice": current,
        "regularMarketPreviousClose": previous,
        "shortName": name,
        "longName": name,
        "longBusinessSummary": f"{name} — акция, торгуется на Московской бирже (MOEX).",
        "currency": "RUB",
        "marketCap": None,
        "trailingPE": None,
        "trailingEps": None,
        "revenueGrowth": None,
        "sector": "MOEX",
        "fiftyTwoWeekHigh": _num(md.get("HIGH")),
        "fiftyTwoWeekLow": _num(md.get("LOW")),
        "_source": "moex",
        "_market": "moex",
    }
    cache_set(cache_key, info, 120)
    return info


def fetch_moex_history(ticker: str, range_: str) -> tuple[list[dict], str]:
    ticker = normalize_moex_ticker(ticker)[0]
    days = _HISTORY_DAYS.get(range_, 96)
    start = date.today() - timedelta(days=days)
    end = date.today()

    payload = _iss_get(
        f"/engines/stock/markets/shares/boards/{_BOARD}/securities/{ticker}/candles.json",
        {
            "iss.meta": "off",
            "from": start.isoformat(),
            "till": end.isoformat(),
            "interval": 24,
        },
    )
    rows = _table(payload, "candles")
    points: list[dict] = []
    for row in rows:
        close = _num(row.get("close"))
        if close is None:
            continue
        begin = str(row.get("begin") or "")[:10]
        if not begin:
            continue
        points.append({"date": begin, "close": round(close, 4), "volume": _num(row.get("volume"))})

    if len(points) < 2:
        raise ValueError(f"Insufficient MOEX history for {ticker}")

    points.sort(key=lambda p: p["date"])
    return points, "RUB"


def fetch_moex_dividends(ticker: str) -> list[dict[str, Any]]:
    ticker = normalize_moex_ticker(ticker)[0]
    cache_key = f"moex:dividends:{ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = _iss_get(f"/securities/{ticker}/dividends.json", {"iss.meta": "off"})
        rows = _table(payload, "dividends")
    except Exception as exc:
        logger.warning("MOEX dividends failed for %s: %s", ticker, exc)
        rows = []

    events: list[dict[str, Any]] = []
    for row in rows:
        value = _num(row.get("value"))
        if value is None:
            continue
        registry = str(row.get("registryclosedate") or row.get("recorddate") or "")[:10]
        if not registry:
            continue
        events.append(
            {
                "ticker": ticker,
                "ex_date": registry,
                "pay_date": str(row.get("closedate") or registry)[:10],
                "amount": round(value, 4),
                "currency": str(row.get("currencyid") or "RUB").upper(),
                "market": "moex",
            }
        )

    events.sort(key=lambda e: e["ex_date"], reverse=True)
    cache_set(cache_key, events, 3600)
    return events


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
        if result != result:
            return None
        return result
    except (TypeError, ValueError):
        return None
