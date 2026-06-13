import logging
from typing import Any

import yfinance as yf
from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import cache_get, cache_set
from app.schemas import StockDetail, StockQuote

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
        if result != result:
            return None
        return result
    except (TypeError, ValueError):
        return None


class StockService:
    """Yahoo Finance integration for stock market data."""

    def __init__(self, cache_ttl: int | None = None) -> None:
        self.cache_ttl = cache_ttl or settings.stock_cache_ttl_seconds

    def get_stock(self, ticker: str) -> StockDetail:
        symbol = ticker.strip().upper()
        cache_key = f"stock:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return StockDetail(**cached)

        info, history = self._fetch_yahoo(symbol)
        current = self._resolve_price(info, history)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price data for {symbol}",
            )

        revenue_growth_raw = _safe_float(info.get("revenueGrowth"))
        revenue_growth = (
            round(revenue_growth_raw * 100, 2) if revenue_growth_raw is not None else None
        )

        detail = StockDetail(
            ticker=symbol,
            name=str(info.get("shortName") or info.get("longName") or symbol),
            currency=str(info.get("currency") or "USD"),
            current_price=round(current, 2),
            market_cap=_safe_float(info.get("marketCap")),
            pe_ratio=_safe_float(info.get("trailingPE") or info.get("forwardPE")),
            eps=_safe_float(info.get("trailingEps") or info.get("epsTrailingTwelveMonths")),
            revenue_growth=revenue_growth,
        )
        cache_set(cache_key, detail.model_dump(), self.cache_ttl)
        return detail

    def get_quote(self, ticker: str) -> StockQuote:
        symbol = ticker.strip().upper()
        cache_key = f"quote:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return StockQuote(**cached)

        info, history = self._fetch_yahoo(symbol)
        current = self._resolve_price(info, history)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price data for {symbol}",
            )

        previous = _safe_float(info.get("regularMarketPreviousClose")) or current
        if previous == current and len(history) > 1:
            previous = float(history["Close"].iloc[-2])

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
        cache_set(cache_key, quote.model_dump(), self.cache_ttl)
        return quote

    def get_quotes(self, tickers: list[str]) -> dict[str, StockQuote]:
        result: dict[str, StockQuote] = {}
        for ticker in tickers:
            try:
                result[ticker.upper()] = self.get_quote(ticker)
            except HTTPException:
                continue
        return result

    def _fetch_yahoo(self, symbol: str):
        try:
            stock = yf.Ticker(symbol)
            info = stock.info or {}
            history = stock.history(period="5d")
        except Exception as exc:
            logger.exception("Failed to fetch Yahoo Finance data for %s", symbol)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to fetch data for {symbol}",
            ) from exc

        if history.empty and not info.get("regularMarketPrice") and not info.get("currentPrice"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticker {symbol} not found",
            )
        return info, history

    @staticmethod
    def _resolve_price(info: dict, history) -> float | None:
        current = _safe_float(info.get("regularMarketPrice") or info.get("currentPrice"))
        if current is None and not history.empty:
            current = float(history["Close"].iloc[-1])
        return current


stock_service = StockService()


def fetch_stock_quote(ticker: str) -> StockQuote:
    return stock_service.get_quote(ticker)


def fetch_quotes(tickers: list[str]) -> dict[str, StockQuote]:
    return stock_service.get_quotes(tickers)
