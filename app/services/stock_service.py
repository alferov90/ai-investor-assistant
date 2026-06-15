import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import cache_get, cache_set
from app.schemas import CompanyProfile, StockDetail, StockQuote

logger = logging.getLogger(__name__)
TWELVE_DATA_TIMEOUT_SECONDS = 10

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="market")
_EMPTY_HISTORY: list[float] = []


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


def _httpx_client() -> httpx.Client:
    kwargs: dict = {
        "timeout": settings.yahoo_fetch_timeout_seconds,
        "headers": {"User-Agent": _USER_AGENT},
        "follow_redirects": True,
        "transport": httpx.HTTPTransport(local_address="0.0.0.0"),
    }
    if settings.yahoo_proxy_url:
        kwargs["proxy"] = settings.yahoo_proxy_url
    return httpx.Client(**kwargs)


def _run_with_timeout(func, *args):
    future = _executor.submit(func, *args)
    return future.result(timeout=settings.yahoo_fetch_timeout_seconds)


def _fetch_twelve_data(symbol: str) -> dict[str, Any]:
    token = settings.twelve_data_api_key
    if not token:
        raise ValueError("Twelve Data API key not configured")

    response = httpx.get(
        "https://api.twelvedata.com/quote",
        params={"symbol": symbol, "apikey": token},
        timeout=TWELVE_DATA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "error":
        raise ValueError(data.get("message") or f"No Twelve Data quote for {symbol}")

    current = _safe_float(data.get("close"))
    if current is None:
        raise ValueError(f"No price in Twelve Data for {symbol}")

    previous = _safe_float(data.get("previous_close")) or current
    fifty_two = data.get("fifty_two_week") or {}

    return {
        "regularMarketPrice": current,
        "regularMarketPreviousClose": previous,
        "shortName": str(data.get("name") or symbol),
        "longName": str(data.get("name") or symbol),
        "currency": str(data.get("currency") or "USD"),
        "fiftyTwoWeekHigh": _safe_float(fifty_two.get("high")),
        "fiftyTwoWeekLow": _safe_float(fifty_two.get("low")),
        "_source": "twelve_data",
    }


def _fetch_yahoo_chart(symbol: str) -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d", "includePrePost": "false"}

    with _httpx_client() as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    results = payload.get("chart", {}).get("result") or []
    if not results:
        raise ValueError(f"No Yahoo chart data for {symbol}")

    meta = dict(results[0].get("meta") or {})
    price = _safe_float(
        meta.get("regularMarketPrice")
        or meta.get("previousClose")
        or meta.get("chartPreviousClose")
    )
    if price is None:
        quotes = (results[0].get("indicators") or {}).get("quote") or [{}]
        closes = quotes[0].get("close") or []
        for value in reversed(closes):
            parsed = _safe_float(value)
            if parsed is not None:
                price = parsed
                break

    if price is None:
        raise ValueError(f"No price in Yahoo chart for {symbol}")

    meta["regularMarketPrice"] = price
    meta.setdefault("shortName", symbol)
    meta.setdefault("longName", symbol)
    meta.setdefault("currency", "USD")
    meta["_source"] = "yahoo"
    return meta


def _fetch_stooq(symbol: str) -> dict[str, Any]:
    stooq_symbol = f"{symbol.lower()}.us"

    with _httpx_client() as client:
        response = client.get(
            "https://stooq.com/q/d/l/",
            params={"s": stooq_symbol, "i": "d"},
        )
        response.raise_for_status()
        lines = [line.strip() for line in response.text.strip().splitlines() if line.strip()]

    if len(lines) < 2:
        raise ValueError(f"No Stooq data for {symbol}")

    last = lines[-1].split(",")
    if len(last) < 7:
        raise ValueError(f"Invalid Stooq response for {symbol}")

    close = _safe_float(last[6])
    if close is None:
        raise ValueError(f"No Stooq price for {symbol}")

    previous = close
    if len(lines) >= 3:
        prev_parts = lines[-2].split(",")
        if len(prev_parts) >= 7:
            previous = _safe_float(prev_parts[6]) or close

    return {
        "regularMarketPrice": close,
        "regularMarketPreviousClose": previous,
        "shortName": symbol,
        "longName": symbol,
        "currency": "USD",
        "_source": "stooq",
    }


def _fetch_finnhub(symbol: str) -> dict[str, Any]:
    token = settings.finnhub_api_key
    if not token:
        raise ValueError("Finnhub API key not configured")

    base = "https://finnhub.io/api/v1"
    params = {"symbol": symbol, "token": token}

    with _httpx_client() as client:
        quote_resp = client.get(f"{base}/quote", params=params)
        quote_resp.raise_for_status()
        quote = quote_resp.json()

        profile: dict = {}
        profile_resp = client.get(f"{base}/stock/profile2", params=params)
        if profile_resp.status_code == 200:
            profile = profile_resp.json() or {}

        metrics: dict = {}
        metrics_resp = client.get(f"{base}/stock/metric", params={**params, "metric": "all"})
        if metrics_resp.status_code == 200:
            metrics = (metrics_resp.json() or {}).get("metric") or {}

    current = _safe_float(quote.get("c"))
    if not current:
        raise ValueError(f"No Finnhub quote for {symbol}")

    market_cap = profile.get("marketCapitalization")
    if market_cap is not None:
        market_cap = float(market_cap) * 1_000_000

    revenue_growth = _safe_float(metrics.get("revenueGrowthQuarterlyYoy"))
    if revenue_growth is not None:
        revenue_growth = revenue_growth / 100

    return {
        "regularMarketPrice": current,
        "regularMarketPreviousClose": _safe_float(quote.get("pc")) or current,
        "shortName": profile.get("name") or symbol,
        "longName": profile.get("name") or symbol,
        "longBusinessSummary": profile.get("description") or "",
        "currency": profile.get("currency") or "USD",
        "marketCap": market_cap,
        "trailingPE": _safe_float(metrics.get("peBasicExclExtraTTM")),
        "trailingEps": _safe_float(metrics.get("epsBasicExclExtraItemsTTM")),
        "revenueGrowth": revenue_growth,
        "sector": profile.get("finnhubIndustry"),
        "fiftyTwoWeekHigh": _safe_float(metrics.get("52WeekHigh")),
        "fiftyTwoWeekLow": _safe_float(metrics.get("52WeekLow")),
        "_source": "finnhub",
    }


def fetch_market_data(symbol: str) -> tuple[dict[str, Any], list[float]]:
    """Finnhub fundamentals → Twelve Data → Yahoo Chart → Stooq."""
    symbol = symbol.strip().upper()
    providers: list[tuple[str, Any]] = []

    if settings.finnhub_api_key:
        providers.append(("finnhub", _fetch_finnhub))
    if settings.twelve_data_api_key:
        providers.append(("twelve_data", _fetch_twelve_data))
    providers.append(("yahoo", _fetch_yahoo_chart))
    providers.append(("stooq", _fetch_stooq))

    for name, fetcher in providers:
        try:
            info = _run_with_timeout(fetcher, symbol)
            logger.info("Market data for %s via %s", symbol, name)
            return info, _EMPTY_HISTORY
        except FuturesTimeoutError:
            logger.warning("%s timeout for %s", name, symbol)
        except Exception as exc:
            logger.warning("%s failed for %s: %s", name, symbol, exc)

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=(
            f"Unable to fetch data for {symbol}. "
            "Add TWELVE_DATA_API_KEY, FINNHUB_API_KEY, or YAHOO_PROXY_URL to .env"
        ),
    )


class StockService:
    """Stock market data: Finnhub / Twelve Data / Yahoo / Stooq."""

    def __init__(self, cache_ttl: int | None = None) -> None:
        self.cache_ttl = cache_ttl or settings.stock_cache_ttl_seconds

    def get_stock(self, ticker: str) -> StockDetail:
        symbol = ticker.strip().upper()
        cache_key = f"stock:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return StockDetail(**cached)

        info, history = fetch_market_data(symbol)
        detail = self._build_stock_detail(symbol, info, history)
        cache_set(cache_key, detail.model_dump(), self.cache_ttl)
        return detail

    def get_company_profile(self, ticker: str) -> CompanyProfile:
        symbol = ticker.strip().upper()
        cache_key = f"profile:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return CompanyProfile(**cached)

        info, history = fetch_market_data(symbol)
        financials = self._build_stock_detail(symbol, info, history)
        description = str(
            info.get("longBusinessSummary") or info.get("description") or "Описание компании недоступно."
        )
        if len(description) > 3000:
            description = description[:2997] + "..."

        profile = CompanyProfile(
            ticker=symbol,
            name=financials.name,
            description=description,
            sector=info.get("sector"),
            industry=info.get("industry"),
            financials=financials,
        )
        cache_set(cache_key, profile.model_dump(), self.cache_ttl)
        cache_set(f"stock:{symbol}", financials.model_dump(), self.cache_ttl)
        return profile

    def _build_stock_detail(self, symbol: str, info: dict, history: list[float]) -> StockDetail:
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

        return StockDetail(
            ticker=symbol,
            name=str(info.get("shortName") or info.get("longName") or symbol),
            currency=str(info.get("currency") or "USD"),
            current_price=round(current, 2),
            market_cap=_safe_float(info.get("marketCap")),
            pe_ratio=_safe_float(info.get("trailingPE")),
            eps=_safe_float(info.get("trailingEps")),
            revenue_growth=revenue_growth,
        )

    def get_quote(self, ticker: str) -> StockQuote:
        symbol = ticker.strip().upper()
        cache_key = f"quote:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return StockQuote(**cached)

        info, history = fetch_market_data(symbol)
        current = self._resolve_price(info, history)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price data for {symbol}",
            )

        previous = _safe_float(info.get("regularMarketPreviousClose")) or current
        if previous == current and len(history) > 1:
            previous = history[-2]

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

    @staticmethod
    def _resolve_price(info: dict, history: list[float]) -> float | None:
        current = _safe_float(info.get("regularMarketPrice") or info.get("currentPrice"))
        if current is None and history:
            current = history[-1]
        return current


stock_service = StockService()


def fetch_stock_quote(ticker: str) -> StockQuote:
    return stock_service.get_quote(ticker)


def fetch_quotes(tickers: list[str]) -> dict[str, StockQuote]:
    return stock_service.get_quotes(tickers)
