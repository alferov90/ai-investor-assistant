import html
import logging
from datetime import date

from sqlalchemy.orm import Session

from app import crud
from app.models import User
from app.redis_client import cache_get, cache_set
from app.services.stock_service import stock_service
from app.telegram_client import is_configured, send_message

logger = logging.getLogger(__name__)

_CONDITION_LABELS = {
    "above": "выше",
    "below": "ниже",
    "change_up": "рост ≥",
    "change_down": "падение ≥",
}


def _esc(text: str) -> str:
    return html.escape(str(text))


def build_portfolio_digest(db: Session, user: User) -> str | None:
    holdings = crud.list_holdings(db, user.id)
    if not holdings:
        return None

    tickers = [h.ticker for h in holdings]
    quotes = stock_service.get_quotes(tickers)
    prices = {t: q.price for t, q in quotes.items()}

    total_cost, total_value = crud.portfolio_totals(holdings, prices)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    sign = "+" if total_pnl >= 0 else ""

    lines = [
        f"☀️ <b>Утренний дайджест</b> — {_esc(user.name)}",
        f"📅 {date.today().isoformat()}",
        "",
        f"💼 Портфель: <b>${total_value:.2f}</b>",
        f"📈 P/L: {sign}${total_pnl:.2f} ({sign}{total_pnl_pct:.1f}%)",
        "",
        "<b>Позиции:</b>",
    ]

    movers: list[tuple[float, str]] = []
    for holding in holdings:
        shares = float(holding.shares)
        avg_price = float(holding.avg_price)
        quote = quotes.get(holding.ticker)
        price = prices.get(holding.ticker, avg_price)
        change_pct = quote.change_percent if quote else 0.0
        value = shares * price
        lines.append(
            f"• <b>{_esc(holding.ticker)}</b> ${price:.2f} "
            f"({change_pct:+.1f}%) — ${value:.2f}"
        )
        movers.append((change_pct, holding.ticker))

    movers.sort(key=lambda x: x[0], reverse=True)
    if len(movers) >= 2:
        best = movers[0]
        worst = movers[-1]
        lines.extend(
            [
                "",
                f"🟢 Лидер дня: <b>{_esc(best[1])}</b> ({best[0]:+.1f}%)",
                f"🔴 Аутсайдер: <b>{_esc(worst[1])}</b> ({worst[0]:+.1f}%)",
            ]
        )

    watchlist = crud.list_watchlist(db, user.id)
    if watchlist:
        wl_tickers = [w.ticker for w in watchlist[:5]]
        wl_quotes = stock_service.get_quotes(wl_tickers)
        lines.append("")
        lines.append(f"<b>Watchlist ({len(watchlist)}):</b>")
        for ticker in wl_tickers:
            q = wl_quotes.get(ticker)
            if q:
                lines.append(f"• {_esc(ticker)} ${q.price:.2f} ({q.change_percent:+.1f}%)")

    alerts = [a for a in crud.list_alerts(db, user.id) if a.is_active]
    if alerts:
        lines.append("")
        lines.append(f"🔔 Активных алертов: {len(alerts)}")

    lines.append("")
    lines.append("/analyze TICKER — AI-анализ · /portfolio — детали")
    return "\n".join(lines)


def send_morning_digests(db: Session) -> int:
    if not is_configured():
        return 0

    today = date.today().isoformat()
    sent = 0
    for user in crud.list_telegram_users(db):
        dedup_key = f"digest:{user.id}:{today}"
        if cache_get(dedup_key):
            continue

        text = build_portfolio_digest(db, user)
        if not text or not user.telegram_chat_id:
            continue

        if send_message(user.telegram_chat_id, text):
            cache_set(dedup_key, True, 86400)
            sent += 1
            logger.info("Morning digest sent to user %s", user.id)

    return sent
