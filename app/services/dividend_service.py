"""Portfolio dividend calendar and yield estimates."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app import crud, schemas
from app.services.fx_service import get_usd_rub_rate, to_rub, to_usd
from app.services.holdings_sync import compute_transaction_summary
from app.services.moex_service import fetch_moex_dividends, is_moex_ticker
from app.services.stock_service import fetch_quotes

logger = logging.getLogger(__name__)


def _estimate_annual_dividend(recent: list[dict]) -> float:
    if not recent:
        return 0.0
    year_ago = date.today().replace(year=date.today().year - 1)
    total = 0.0
    for event in recent:
        try:
            ex = date.fromisoformat(event["ex_date"])
        except ValueError:
            continue
        if ex >= year_ago:
            total += float(event["amount"])
    if total > 0:
        return total
    return float(recent[0]["amount"]) * 4 if recent else 0.0


def get_ticker_dividends(ticker: str) -> list[schemas.DividendEvent]:
    if not is_moex_ticker(ticker):
        return []
    try:
        rows = fetch_moex_dividends(ticker)
    except Exception as exc:
        logger.warning("Dividends failed for %s: %s", ticker, exc)
        return []
    return [schemas.DividendEvent(**row) for row in rows]


def get_portfolio_dividends(db: Session, user_id: int) -> schemas.PortfolioDividends:
    holdings = crud.list_holdings(db, user_id)
    usd_rub = get_usd_rub_rate()
    txn_summary = compute_transaction_summary(db, user_id)

    if not holdings:
        return schemas.PortfolioDividends(
            usd_rub_rate=round(usd_rub, 4),
            total_annual_income_usd=0,
            total_annual_income_rub=0,
            dividends_received=txn_summary.get("dividends_total", 0),
            holdings=[],
            upcoming=[],
        )

    tickers = [h.ticker for h in holdings]
    quotes = fetch_quotes(tickers)
    summaries: list[schemas.HoldingDividendSummary] = []
    upcoming: list[schemas.DividendEvent] = []
    total_annual_usd = 0.0
    today = date.today().isoformat()

    for holding in holdings:
        ticker = holding.ticker
        shares = float(holding.shares)
        quote = quotes.get(ticker)
        currency = quote.currency if quote else ("RUB" if is_moex_ticker(ticker) else "USD")
        price = quote.price if quote else float(holding.avg_price)
        name = quote.name if quote else ticker

        events = get_ticker_dividends(ticker) if is_moex_ticker(ticker) else []
        annual_per_share = _estimate_annual_dividend([e.model_dump() for e in events])
        annual_income = annual_per_share * shares if annual_per_share else None
        div_yield = (annual_per_share / price * 100) if annual_per_share and price else None

        if annual_income:
            total_annual_usd += to_usd(annual_income, currency)

        next_div = next((e for e in events if e.ex_date >= today), None)
        if next_div:
            upcoming.append(next_div)

        summaries.append(
            schemas.HoldingDividendSummary(
                ticker=ticker,
                name=name,
                shares=shares,
                currency=currency,
                market="moex" if is_moex_ticker(ticker) else "us",
                price=round(price, 2),
                dividend_yield=round(div_yield, 2) if div_yield is not None else None,
                annual_income=round(annual_income, 2) if annual_income else None,
                next_dividend=next_div,
                recent_dividends=events[:4],
            )
        )

    upcoming.sort(key=lambda e: e.ex_date)
    summaries.sort(key=lambda h: h.annual_income or 0, reverse=True)

    return schemas.PortfolioDividends(
        usd_rub_rate=round(usd_rub, 4),
        total_annual_income_usd=round(total_annual_usd, 2),
        total_annual_income_rub=round(to_rub(total_annual_usd, "USD"), 2),
        dividends_received=txn_summary.get("dividends_total", 0),
        holdings=summaries,
        upcoming=upcoming[:12],
    )
