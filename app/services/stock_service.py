import logging

import yfinance as yf
from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import cache_get, cache_set
from app.schemas import StockQuote

logger = logging.getLogger(__name__)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
        if result != result:  # NaN
            return None
        return result
    except (TypeError, ValueError):
        return None


def fetch_stock_quote(ticker: str) -> StockQuote:
    symbol = ticker.strip().upper()
    cache_key = f"quote:{symbol}"
    cached = cache_get(cache_key)
    if cached:
        return StockQuote(**cached)

    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        history = stock.history(period="5d")
    except Exception as exc:
        logger.exception("Failed to fetch quote for %s", symbol)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to fetch data for {symbol}",
        ) from exc

    if history.empty and not info.get("regularMarketPrice"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticker {symbol} not found",
        )

    current = _safe_float(info.get("regularMarketPrice"))
    previous = _safe_float(info.get("regularMarketPreviousClose"))
    if current is None and not history.empty:
        current = float(history["Close"].iloc[-1])
        previous = float(history["Close"].iloc[-2]) if len(history) > 1 else current
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price data for {symbol}",
        )

    previous = previous or current
    change = current - previous
    change_percent = (change / previous * 100) if previous else 0.0

    quote = StockQuote(
        ticker=symbol,
        name=str(info.get("shortName") or info.get("longName") or symbol),
        price=round(current, 2),
        change=round(change, 2),
        change_percent=round(change_percent, 2),
        currency=str(info.get("currency") or "USD"),
        market_cap=_safe_float(info.get("marketCap")),
        pe_ratio=_safe_float(info.get("trailingPE")),
        fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
        fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
        sector=info.get("sector"),
        industry=info.get("industry"),
    )
    cache_set(cache_key, quote.model_dump(), settings.stock_cache_ttl_seconds)
    return quote


def fetch_quotes(tickers: list[str]) -> dict[str, StockQuote]:
    result: dict[str, StockQuote] = {}
    for ticker in tickers:
        try:
            result[ticker.upper()] = fetch_stock_quote(ticker)
        except HTTPException:
            continue
    return result
