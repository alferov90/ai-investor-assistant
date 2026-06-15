"""Portfolio benchmark vs index and rule-based risk analysis."""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.services.stock_service import fetch_price_history, fetch_quotes

logger = logging.getLogger(__name__)

_BENCHMARKS = frozenset({"SPY", "QQQ"})
_RANGES = frozenset({"1mo", "3mo", "6mo", "1y"})

_CONCENTRATION_WARN = 25.0
_CONCENTRATION_DANGER = 40.0
_SECTOR_WARN = 40.0
_SECTOR_DANGER = 60.0
_TOP3_WARN = 70.0
_DRAWDOWN_WARN = 15.0
_DRAWDOWN_DANGER = 25.0


def _enrich_holdings(db: Session, user_id: int) -> tuple[list[dict], float, dict]:
    holdings = crud.list_holdings(db, user_id)
    if not holdings:
        return [], 0.0, {}

    tickers = [h.ticker for h in holdings]
    quotes = fetch_quotes(tickers)
    prices = {t: q.price for t, q in quotes.items()}

    total_cost, total_value = crud.portfolio_totals(holdings, prices)
    if total_value <= 0:
        return [], 0.0, quotes

    enriched: list[dict] = []
    for holding in holdings:
        shares = float(holding.shares)
        avg_price = float(holding.avg_price)
        price = prices.get(holding.ticker, avg_price)
        value = shares * price
        cost = shares * avg_price
        pnl = value - cost
        quote = quotes.get(holding.ticker)
        enriched.append(
            {
                "ticker": holding.ticker,
                "name": quote.name if quote else holding.ticker,
                "shares": shares,
                "price": price,
                "value": round(value, 2),
                "cost": round(cost, 2),
                "pnl": round(pnl, 2),
                "pnl_percent": round((pnl / cost * 100) if cost else 0, 2),
                "weight_pct": round(value / total_value * 100, 2),
                "sector": (quote.sector if quote and quote.sector else None) or "Неизвестно",
            }
        )

    enriched.sort(key=lambda x: x["value"], reverse=True)
    return enriched, total_value, quotes


def _history_map(ticker: str, range_: str) -> dict[str, float]:
    history = fetch_price_history(ticker, range_)
    return {p.date: p.close for p in history.points}


def _forward_fill_series(
    dates: list[str], price_by_date: dict[str, float]
) -> list[float | None]:
    values: list[float | None] = []
    last: float | None = None
    for d in dates:
        if d in price_by_date:
            last = price_by_date[d]
        values.append(last)
    return values


def _max_drawdown(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 2)


def _build_index_series(
    weights: dict[str, float],
    histories: dict[str, dict[str, float]],
    dates: list[str],
) -> list[float]:
    base_prices: dict[str, float] = {}
    for ticker in weights:
        series = histories.get(ticker, {})
        for d in dates:
            if d in series:
                base_prices[ticker] = series[d]
                break

    active = {t: w for t, w in weights.items() if t in base_prices}
    total_w = sum(active.values())
    if total_w <= 0:
        raise ValueError("No price history for portfolio holdings")

    active = {t: w / total_w for t, w in active.items()}
    filled = {
        t: _forward_fill_series(dates, histories.get(t, {})) for t in active
    }

    index_values: list[float] = []
    for i, _date in enumerate(dates):
        component = 0.0
        for ticker, w in active.items():
            price = filled[ticker][i]
            if price is None or base_prices[ticker] <= 0:
                continue
            component += w * (price / base_prices[ticker])
        index_values.append(round(component * 100, 2))

    # Back-fill any leading gaps with first valid value
    first_valid = next((v for v in index_values if v > 0), 100.0)
    return [v if v > 0 else first_valid for v in index_values]


def compute_benchmark(
    db: Session,
    user_id: int,
    benchmark: str = "SPY",
    range_: str = "3mo",
) -> schemas.PortfolioBenchmark:
    benchmark = benchmark.strip().upper()
    if benchmark not in _BENCHMARKS:
        benchmark = "SPY"
    if range_ not in _RANGES:
        range_ = "3mo"

    enriched, total_value, _ = _enrich_holdings(db, user_id)
    if not enriched or total_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portfolio is empty",
        )

    weights = {h["ticker"]: h["value"] / total_value for h in enriched}

    try:
        bench_hist = _history_map(benchmark, range_)
    except Exception as exc:
        logger.warning("Benchmark history failed for %s: %s", benchmark, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to fetch benchmark {benchmark} history",
        ) from exc

    dates = sorted(bench_hist.keys())
    if len(dates) < 2:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Insufficient benchmark data",
        )

    histories: dict[str, dict[str, float]] = {benchmark: bench_hist}
    for ticker in weights:
        try:
            histories[ticker] = _history_map(ticker, range_)
        except Exception as exc:
            logger.warning("History failed for %s: %s", ticker, exc)

    try:
        portfolio_series = _build_index_series(weights, histories, dates)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    bench_base = bench_hist[dates[0]]
    bench_series = [
        round(bench_hist[d] / bench_base * 100, 2) if bench_base else 100.0
        for d in dates
    ]

    points = [
        schemas.BenchmarkPoint(date=d, portfolio=portfolio_series[i], benchmark=bench_series[i])
        for i, d in enumerate(dates)
    ]

    port_return = round(portfolio_series[-1] - 100, 2)
    bench_return = round(bench_series[-1] - 100, 2)

    return schemas.PortfolioBenchmark(
        benchmark=benchmark,
        range=range_,
        portfolio_return=port_return,
        benchmark_return=bench_return,
        alpha=round(port_return - bench_return, 2),
        max_drawdown_pct=_max_drawdown(portfolio_series),
        points=points,
    )


def _alert(level: str, code: str, title: str, message: str) -> schemas.RiskAlert:
    return schemas.RiskAlert(level=level, code=code, title=title, message=message)


def compute_risks(db: Session, user_id: int, range_: str = "3mo") -> schemas.PortfolioRisks:
    if range_ not in _RANGES:
        range_ = "3mo"

    enriched, total_value, _ = _enrich_holdings(db, user_id)
    if not enriched:
        return schemas.PortfolioRisks(
            score=0,
            level="ok",
            alerts=[_alert("info", "empty", "Портфель пуст", "Добавьте позиции для анализа рисков.")],
            concentration=[],
            sectors=[],
            max_drawdown_pct=None,
        )

    alerts: list[schemas.RiskAlert] = []
    concentration = [
        {"ticker": h["ticker"], "weight_pct": h["weight_pct"], "value": h["value"]}
        for h in enriched
    ]

    for h in enriched:
        w = h["weight_pct"]
        if w >= _CONCENTRATION_DANGER:
            alerts.append(
                _alert(
                    "danger",
                    "concentration",
                    f"Высокая концентрация: {h['ticker']}",
                    f"{h['ticker']} составляет {w:.1f}% портфеля — сильная зависимость от одной акции.",
                )
            )
        elif w >= _CONCENTRATION_WARN:
            alerts.append(
                _alert(
                    "warning",
                    "concentration",
                    f"Концентрация: {h['ticker']}",
                    f"{h['ticker']} — {w:.1f}% портфеля. Рекомендуется не более 25% на одну позицию.",
                )
            )

    if len(enriched) < 3:
        alerts.append(
            _alert(
                "info",
                "diversification",
                "Мало позиций",
                f"В портфеле {len(enriched)} поз. — низкая диверсификация.",
            )
        )

    top3_weight = sum(h["weight_pct"] for h in enriched[:3])
    if len(enriched) >= 3 and top3_weight >= _TOP3_WARN:
        alerts.append(
            _alert(
                "warning",
                "top3",
                "Топ-3 доминируют",
                f"Три крупнейшие позиции — {top3_weight:.1f}% портфеля.",
            )
        )

    sector_totals: dict[str, float] = defaultdict(float)
    sector_value: dict[str, float] = defaultdict(float)
    for h in enriched:
        sector_totals[h["sector"]] += h["weight_pct"]
        sector_value[h["sector"]] += h["value"]

    sectors = [
        {
            "sector": name,
            "weight_pct": round(weight, 2),
            "value": round(sector_value[name], 2),
        }
        for name, weight in sorted(sector_totals.items(), key=lambda x: -x[1])
    ]

    for sector, weight in sector_totals.items():
        if sector == "Неизвестно":
            continue
        if weight >= _SECTOR_DANGER:
            alerts.append(
                _alert(
                    "danger",
                    "sector",
                    f"Сектор: {sector}",
                    f"Сектор «{sector}» — {weight:.1f}% портфеля.",
                )
            )
        elif weight >= _SECTOR_WARN:
            alerts.append(
                _alert(
                    "warning",
                    "sector",
                    f"Сектор: {sector}",
                    f"Сектор «{sector}» — {weight:.1f}% портфеля (выше 40%).",
                )
            )

    losers = [h for h in enriched if h["pnl_percent"] < -15]
    for h in losers[:3]:
        alerts.append(
            _alert(
                "warning",
                "loser",
                f"Просадка: {h['ticker']}",
                f"{h['ticker']}: {h['pnl_percent']:+.1f}% от средней цены покупки.",
            )
        )

    max_drawdown: float | None = None
    try:
        weights = {h["ticker"]: h["value"] / total_value for h in enriched}
        bench_hist = _history_map("SPY", range_)
        dates = sorted(bench_hist.keys())
        histories: dict[str, dict[str, float]] = {}
        for ticker in weights:
            try:
                histories[ticker] = _history_map(ticker, range_)
            except Exception:
                pass
        series = _build_index_series(weights, histories, dates)
        max_drawdown = _max_drawdown(series)
        if max_drawdown >= _DRAWDOWN_DANGER:
            alerts.append(
                _alert(
                    "danger",
                    "drawdown",
                    "Сильная просадка",
                    f"Максимальная просадка за период — {max_drawdown:.1f}%.",
                )
            )
        elif max_drawdown >= _DRAWDOWN_WARN:
            alerts.append(
                _alert(
                    "warning",
                    "drawdown",
                    "Просадка от пика",
                    f"Максимальная просадка за период — {max_drawdown:.1f}%.",
                )
            )
    except Exception as exc:
        logger.warning("Drawdown calculation failed: %s", exc)

    danger_count = sum(1 for a in alerts if a.level == "danger")
    warning_count = sum(1 for a in alerts if a.level == "warning")
    score = min(100, danger_count * 22 + warning_count * 10 + (5 if len(enriched) < 3 else 0))

    if danger_count > 0:
        level = "high"
    elif warning_count > 0:
        level = "medium"
    elif score > 0:
        level = "low"
    else:
        level = "ok"
        if not alerts:
            alerts.append(
                _alert(
                    "info",
                    "healthy",
                    "Риски под контролем",
                    "Концентрация и сектора в норме. Продолжайте мониторинг.",
                )
            )

    return schemas.PortfolioRisks(
        score=score,
        level=level,
        alerts=alerts,
        concentration=concentration,
        sectors=sectors,
        max_drawdown_pct=max_drawdown,
    )
