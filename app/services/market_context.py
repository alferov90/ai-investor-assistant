"""Company news and earnings calendar for AI context."""

from __future__ import annotations

import logging
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.redis_client import cache_get, cache_set
from app.schemas import EarningsEvent, MarketContext, NewsItem

logger = logging.getLogger(__name__)

NEWS_TRANSLATION_SYSTEM = """Ты переводишь финансовые новости на русский язык.
Сохраняй названия компаний, тикеры, числа, проценты и финансовые термины точно.
Пиши естественно и кратко. Не добавляй фактов, которых нет в исходном тексте.
Верни только валидный JSON."""


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


def _yandex_translation_configured() -> bool:
    return bool(settings.yandex_cloud_api_key and settings.yandex_cloud_folder_id)


def _strip_json_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```")
        content = content.removesuffix("```").strip()
    return content


def _translate_news_items(ticker: str, items: list[NewsItem]) -> list[NewsItem]:
    if not items or not _yandex_translation_configured():
        return items

    payload = [
        {
            "id": index,
            "headline": item.headline[:300],
            "summary": item.summary[:500],
        }
        for index, item in enumerate(items)
    ]
    prompt = (
        "Переведи headline и summary на русский язык для показа в инвестиционном "
        f"интерфейсе. Тикер: {ticker}. Верни JSON строго такого вида: "
        '{"items":[{"id":0,"headline_ru":"...","summary_ru":"..."}]}.\n\n'
        f"Новости:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    body = {
        "modelUri": f"gpt://{settings.yandex_cloud_folder_id}/{settings.yandex_gpt_model}",
        "completionOptions": {
            "stream": False,
            "temperature": 0.15,
            "maxTokens": 3000,
        },
        "messages": [
            {"role": "system", "text": NEWS_TRANSLATION_SYSTEM},
            {"role": "user", "text": prompt},
        ],
    }

    try:
        response = httpx.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            json=body,
            headers={
                "Authorization": f"Api-Key {settings.yandex_cloud_api_key}",
                "Content-Type": "application/json",
            },
            timeout=45,
        )
        response.raise_for_status()
        content = response.json()["result"]["alternatives"][0]["message"]["text"]
        data = json.loads(_strip_json_fence(content))
    except Exception as exc:
        logger.warning("YandexGPT news translation failed for %s: %s", ticker, exc)
        return items

    translated = data.get("items") if isinstance(data, dict) else None
    if not isinstance(translated, list):
        return items

    by_id = {
        row.get("id"): row
        for row in translated
        if isinstance(row, dict) and isinstance(row.get("id"), int)
    }
    for index, item in enumerate(items):
        row = by_id.get(index)
        if not row:
            continue
        headline_ru = str(row.get("headline_ru") or "").strip()
        summary_ru = str(row.get("summary_ru") or "").strip()
        if headline_ru:
            item.headline_ru = headline_ru
        if summary_ru:
            item.summary_ru = summary_ru
    return items


def fetch_company_news(ticker: str, days: int = 14) -> list[NewsItem]:
    ticker = ticker.strip().upper()
    cache_key = f"news:{ticker}:{days}"
    cached = cache_get(cache_key)
    if cached:
        items = [NewsItem(**item) for item in cached]
        if _yandex_translation_configured() and any(not item.headline_ru for item in items):
            items = _translate_news_items(ticker, items)
            cache_set(cache_key, [i.model_dump(mode="json") for i in items], 900)
        return items

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

    items = _translate_news_items(ticker, items)
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
