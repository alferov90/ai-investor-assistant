"""Multi-currency portfolio valuation."""

from __future__ import annotations

from app import models
from app.services.fx_service import to_rub, to_usd
from app.services.moex_service import is_moex_ticker
from app.schemas import StockQuote


def enrich_holdings(
    holdings: list[models.PortfolioHolding],
    quotes: dict[str, StockQuote],
) -> tuple[list[dict], float, float, float, float, float]:
    """Returns enriched rows, cost_usd, value_usd, pnl_usd, cost_rub, value_rub."""
    total_cost_usd = 0.0
    total_value_usd = 0.0
    enriched: list[dict] = []

    for holding in holdings:
        shares = float(holding.shares)
        avg_price = float(holding.avg_price)
        quote = quotes.get(holding.ticker)
        currency = quote.currency if quote else ("RUB" if is_moex_ticker(holding.ticker) else "USD")
        market = "moex" if is_moex_ticker(holding.ticker) else "us"
        price = quote.price if quote else avg_price
        value_local = shares * price
        cost_local = shares * avg_price
        pnl_local = value_local - cost_local

        cost_usd = to_usd(cost_local, currency)
        value_usd = to_usd(value_local, currency)
        pnl_usd = value_usd - cost_usd
        total_cost_usd += cost_usd
        total_value_usd += value_usd

        enriched.append(
            {
                "ticker": holding.ticker,
                "name": quote.name if quote else holding.ticker,
                "shares": shares,
                "price": round(price, 2),
                "avg_price": round(avg_price, 2),
                "currency": currency,
                "market": market,
                "value": round(value_local, 2),
                "value_usd": round(value_usd, 2),
                "value_rub": round(to_rub(value_local, currency), 2),
                "cost": round(cost_local, 2),
                "pnl": round(pnl_local, 2),
                "pnl_usd": round(pnl_usd, 2),
                "pnl_percent": round((pnl_local / cost_local * 100) if cost_local else 0, 2),
            }
        )

    enriched.sort(key=lambda x: x["value_usd"], reverse=True)
    total_pnl_usd = total_value_usd - total_cost_usd
    return (
        enriched,
        round(total_cost_usd, 2),
        round(total_value_usd, 2),
        round(total_pnl_usd, 2),
        round(to_rub(total_cost_usd, "USD"), 2),
        round(to_rub(total_value_usd, "USD"), 2),
    )
