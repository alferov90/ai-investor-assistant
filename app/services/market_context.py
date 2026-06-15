"""Company news and earnings calendar for AI context."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.redis_client import cache_get, cache_set
from app.schemas import EarningsEvent, MarketContext, NewsItem

logger = logging.getLogger(__name__)


def _finnhub_get(path: str, params: dict | None = None) -> Any:
    token = settings.finnhub_api_key
    if not token:
        raise ValueError("Finnhub API key not configured")

    query = {"token": token, **(params or {})}
    response = httpx.get(
        f"https://finnhub.io/api/v1{path}",
        params=query,
        timeout=settings.yahoo_fetch_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def fetch_company_news(ticker: str, days: int = 14) -> list[NewsItem]:
    ticker = ticker.strip().upper()
    cache_key = f"news:{ticker}:{days}"
    cached = cache_get(cache_key)
    if cached:
        return [NewsItem(**item) for item in cached]

    if not settings.finnhub_api_key:
        return []

    end = date.today()
    start = end - timedelta(days=days)
    try:
        payload = _finnhub_get(
            "/company-news",
            {"symbol": ticker, "from": start.isoformat(), "to": end.isoformat()},
        )
    except Exception as exc:
        logger.warning("Finnhub news failed for %s: %s", ticker, exc)
        return []

    items: list[NewsItem] = []
    for row in (payload or [])[:8]:
        ts = row.get("datetime")
        published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
        headline = str(row.get("headline") or "").strip()
        if not headline:
            continue
        summary = str(row.get("summary") or "")[:400]
        items.append(
            NewsItem(
                headline=headline,
                summary=summary,
                source=str(row.get("source") or "Finnhub"),
                published_at=published,
                url=row.get("url"),
            )
        )

    cache_set(cache_key, [i.model_dump(mode="json") for i in items], 900)
    return items


def fetch_earnings(ticker: str) -> list[EarningsEvent]:
    ticker = ticker.strip().upper()
    cache_key = f"earnings:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return [EarningsEvent(**item) for item in cached]

    if not settings.finnhub_api_key:
        return []

    try:
        payload = _finnhub_get("/stock/earnings", {"symbol": ticker})
    except Exception as exc:
        logger.warning("Finnhub earnings failed for %s: %s", ticker, exc)
        return []

    items: list[EarningsEvent] = []
    for row in (payload or [])[:6]:
        period = str(row.get("period") or row.get("quarter") or "")
        items.append(
            EarningsEvent(
                date=str(row.get("date") or row.get("period") or "")[:10],
                period=period or None,
                eps_actual=_safe(row.get("actual")),
                eps_estimate=_safe(row.get("estimate")),
                surprise_pct=_safe(row.get("surprisePercent")),
            )
        )

    cache_set(cache_key, [i.model_dump() for i in items], 3600)
    return items


def fetch_upcoming_earnings(ticker: str) -> EarningsEvent | None:
    ticker = ticker.strip().upper()
    if not settings.finnhub_api_key:
        return None

    today = date.today()
    end = today + timedelta(days=90)
    cache_key = f"earnings_upcoming:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return EarningsEvent(**cached) if cached else None

    try:
        payload = _finnhub_get(
            "/calendar/earnings",
            {"from": today.isoformat(), "to": end.isoformat(), "symbol": ticker},
        )
    except Exception as exc:
        logger.warning("Finnhub earnings calendar failed for %s: %s", ticker, exc)
        return None

    rows = (payload or {}).get("earningsCalendar") or []
    upcoming: EarningsEvent | None = None
    for row in rows:
        if str(row.get("symbol", "")).upper() != ticker:
            continue
        evt_date = str(row.get("date") or "")[:10]
        if not evt_date:
            continue
        upcoming = EarningsEvent(
            date=evt_date,
            period=str(row.get("quarter") or "") or None,
            eps_estimate=_safe(row.get("epsEstimate")),
            revenue_estimate=_safe(row.get("revenueEstimate")),
        )
        break

    cache_set(cache_key, upcoming.model_dump() if upcoming else {}, 3600)
    return upcoming


def _safe(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_market_context(ticker: str) -> MarketContext:
    news = fetch_company_news(ticker)
    earnings = fetch_earnings(ticker)
    upcoming = fetch_upcoming_earnings(ticker)
    return MarketContext(
        ticker=ticker.upper(),
        news=news,
        earnings=earnings,
        upcoming_earnings=upcoming,
    )
