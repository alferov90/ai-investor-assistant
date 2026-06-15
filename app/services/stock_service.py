import logging
import multiprocessing as mp
import socket
import time
from typing import Any

import httpx
import yfinance as yf
from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import cache_get, cache_set
from app.schemas import StockDetail, StockQuote

logger = logging.getLogger(__name__)
YAHOO_TIMEOUT_SECONDS = 8
YAHOO_COOLDOWN_SECONDS = 60
TWELVE_DATA_TIMEOUT_SECONDS = 10
_provider_unavailable_until = 0.0

socket.setdefaulttimeout(YAHOO_TIMEOUT_SECONDS)


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


def _fetch_yahoo_worker(symbol: str, conn) -> None:
    try:
        socket.setdefaulttimeout(YAHOO_TIMEOUT_SECONDS)
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        history = stock.history(period="5d", timeout=YAHOO_TIMEOUT_SECONDS)
        closes = []
        if not history.empty:
            closes = [float(value) for value in history["Close"].dropna().tail(5).tolist()]
        conn.send(("ok", info, closes))
    except Exception as exc:
        conn.send(("error", str(exc)))
    finally:
        conn.close()


class StockService:
    """Market data integration for stock quotes and details."""

    def __init__(self, cache_ttl: int | None = None) -> None:
        self.cache_ttl = cache_ttl or settings.stock_cache_ttl_seconds

    def get_stock(self, ticker: str) -> StockDetail:
        symbol = ticker.strip().upper()
        cache_key = f"stock:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return StockDetail(**cached)

        quote = self.get_quote(symbol)

        detail = StockDetail(
            ticker=symbol,
            name=quote.name,
            currency=quote.currency,
            current_price=quote.price,
            market_cap=quote.market_cap,
            pe_ratio=quote.pe_ratio,
            eps=None,
            revenue_growth=None,
        )
        cache_set(cache_key, detail.model_dump(), self.cache_ttl)
        return detail

    def get_quote(self, ticker: str) -> StockQuote:
        symbol = ticker.strip().upper()
        cache_key = f"quote:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return StockQuote(**cached)

        quote = self._fetch_twelve_data_quote(symbol)
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

    def _fetch_twelve_data_quote(self, symbol: str) -> StockQuote:
        if not settings.twelve_data_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Twelve Data API key is not configured",
            )

        try:
            response = httpx.get(
                "https://api.twelvedata.com/quote",
                params={"symbol": symbol, "apikey": settings.twelve_data_api_key},
                timeout=TWELVE_DATA_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.exception("Failed to fetch Twelve Data quote for %s", symbol)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to fetch market data for {symbol}",
            ) from exc

        if data.get("status") == "error":
            message = data.get("message") or f"Ticker {symbol} not found"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)

        current = _safe_float(data.get("close"))
        previous = _safe_float(data.get("previous_close"))
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price data for {symbol}",
            )

        if previous is None:
            previous = current

        change = _safe_float(data.get("change"))
        if change is None:
            change = current - previous

        change_percent = _safe_float(data.get("percent_change"))
        if change_percent is None:
            change_percent = (change / previous * 100) if previous else 0.0

        return StockQuote(
            ticker=str(data.get("symbol") or symbol).upper(),
            name=str(data.get("name") or symbol),
            price=round(current, 2),
            change=round(change, 2),
            change_percent=round(change_percent, 2),
            currency=str(data.get("currency") or "USD"),
            market_cap=None,
            pe_ratio=None,
            fifty_two_week_high=_safe_float((data.get("fifty_two_week") or {}).get("high")),
            fifty_two_week_low=_safe_float((data.get("fifty_two_week") or {}).get("low")),
            sector=None,
            industry=None,
        )

    def _fetch_yahoo(self, symbol: str):
        global _provider_unavailable_until

        if time.monotonic() < _provider_unavailable_until:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Market data provider is temporarily unavailable",
            )

        try:
            parent_conn, child_conn = mp.Pipe(duplex=False)
            process = mp.Process(target=_fetch_yahoo_worker, args=(symbol, child_conn))
            process.start()
            child_conn.close()

            if not parent_conn.poll(YAHOO_TIMEOUT_SECONDS):
                process.terminate()
                process.join(timeout=2)
                _provider_unavailable_until = time.monotonic() + YAHOO_COOLDOWN_SECONDS
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Market data provider timed out for {symbol}",
                )

            state, *payload = parent_conn.recv()
            process.join(timeout=2)
            if state == "error":
                raise RuntimeError(payload[0])
            info, closes = payload
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            _provider_unavailable_until = time.monotonic() + YAHOO_COOLDOWN_SECONDS
            logger.exception("Failed to fetch Yahoo Finance data for %s", symbol)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to fetch data for {symbol}",
            ) from exc

        if not closes and not info.get("regularMarketPrice") and not info.get("currentPrice"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticker {symbol} not found",
            )
        return info, closes

    @staticmethod
    def _resolve_price(info: dict, closes: list[float]) -> float | None:
        current = _safe_float(info.get("regularMarketPrice") or info.get("currentPrice"))
        if current is None and closes:
            current = closes[-1]
        return current


stock_service = StockService()


def fetch_stock_quote(ticker: str) -> StockQuote:
    return stock_service.get_quote(ticker)


def fetch_quotes(tickers: list[str]) -> dict[str, StockQuote]:
    return stock_service.get_quotes(tickers)
