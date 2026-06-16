"""Compact daily portfolio summary for the dashboard."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import crud, schemas
from app.services.dividend_service import get_portfolio_dividends
from app.services.fx_service import get_usd_rub_rate
from app.services.portfolio_valuation import enrich_holdings
from app.services.stock_service import fetch_quotes


def build_daily_summary(db: Session, user_id: int) -> schemas.PortfolioDailySummary:
    holdings = crud.list_holdings(db, user_id)
    usd_rub = get_usd_rub_rate()
    watchlist = crud.list_watchlist(db, user_id)
    active_alerts = [alert for alert in crud.list_alerts(db, user_id) if alert.is_active]

    if not holdings:
        return schemas.PortfolioDailySummary(
            holdings_count=0,
            total_value_usd=0,
            total_value_rub=0,
            total_pnl_usd=0,
            total_pnl_percent=0,
            usd_rub_rate=round(usd_rub, 4),
            active_alerts_count=len(active_alerts),
            watchlist_count=len(watchlist),
            insights=[
                schemas.DailyInsight(
                    title="Портфель пуст",
                    message="Добавьте первую позицию, чтобы видеть дневную сводку, риски и дивиденды.",
                )
            ],
        )

    tickers = [holding.ticker for holding in holdings]
    quotes = fetch_quotes(tickers)
    enriched, total_cost, total_value, total_pnl, _total_cost_rub, total_value_rub = enrich_holdings(
        holdings, quotes
    )
    total_pnl_percent = (total_pnl / total_cost * 100) if total_cost else 0

    movers: list[schemas.DailyMover] = []
    for ticker, quote in quotes.items():
        movers.append(
            schemas.DailyMover(
                ticker=ticker,
                name=quote.name,
                change_percent=round(quote.change_percent, 2),
                price=quote.price,
                currency=quote.currency,
            )
        )
    movers.sort(key=lambda item: item.change_percent, reverse=True)

    dividends = get_portfolio_dividends(db, user_id)
    insights = _build_insights(
        enriched=enriched,
        holdings_count=len(holdings),
        active_alerts_count=len(active_alerts),
        watchlist_count=len(watchlist),
        upcoming_dividends=dividends.upcoming,
    )

    return schemas.PortfolioDailySummary(
        holdings_count=len(holdings),
        total_value_usd=round(total_value, 2),
        total_value_rub=round(total_value_rub, 2),
        total_pnl_usd=round(total_pnl, 2),
        total_pnl_percent=round(total_pnl_percent, 2),
        usd_rub_rate=round(usd_rub, 4),
        best_mover=movers[0] if movers else None,
        worst_mover=movers[-1] if len(movers) > 1 else None,
        upcoming_dividends=dividends.upcoming[:3],
        active_alerts_count=len(active_alerts),
        watchlist_count=len(watchlist),
        insights=insights,
    )


def _build_insights(
    enriched: list[dict],
    holdings_count: int,
    active_alerts_count: int,
    watchlist_count: int,
    upcoming_dividends: list[schemas.DividendEvent],
) -> list[schemas.DailyInsight]:
    insights: list[schemas.DailyInsight] = []

    if holdings_count < 3:
        insights.append(
            schemas.DailyInsight(
                level="warning",
                title="Мало позиций",
                message="Портфель пока слабо диверсифицирован: добавьте 2-3 независимые идеи перед увеличением риска.",
            )
        )

    if enriched:
        total_value = sum(float(item.get("value_usd") or item.get("value") or 0) for item in enriched)
        top = enriched[0]
        top_value = float(top.get("value_usd") or top.get("value") or 0)
        top_weight = (top_value / total_value * 100) if total_value else 0
        if top_weight >= 35:
            insights.append(
                schemas.DailyInsight(
                    level="warning",
                    title=f"Концентрация в {top['ticker']}",
                    message=f"{top['ticker']} занимает около {top_weight:.0f}% портфеля. Проверьте, комфортен ли такой риск.",
                )
            )

    if upcoming_dividends:
        next_div = upcoming_dividends[0]
        insights.append(
            schemas.DailyInsight(
                title="Ближайший дивиденд",
                message=f"{next_div.ticker}: отсечка {next_div.ex_date}, сумма {next_div.amount:g} {next_div.currency}.",
            )
        )

    if active_alerts_count == 0 and watchlist_count > 0:
        insights.append(
            schemas.DailyInsight(
                title="Watchlist без алертов",
                message="По идеям из watchlist нет активных алертов. Добавьте уровни, чтобы сайт сам напомнил о входе.",
            )
        )

    if not insights:
        insights.append(
            schemas.DailyInsight(
                level="ok",
                title="Портфель под контролем",
                message="Крупных концентраций и срочных действий не найдено. Проверьте новости и алерты по плану.",
            )
        )

    return insights[:4]
