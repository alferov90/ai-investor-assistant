import html
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import crud, models
from app.services.stock_service import stock_service
from app.telegram_client import is_configured, send_message

logger = logging.getLogger(__name__)

CONDITION_LABELS = {
    "above": "цена выше",
    "below": "цена ниже",
    "change_up": "рост за день ≥",
    "change_down": "падение за день ≥",
}


def _esc(text: str) -> str:
    return html.escape(str(text))


def _alert_triggered(alert: models.PriceAlert, price: float, change_percent: float) -> bool:
    target = float(alert.target_value)
    if alert.condition_type == "above":
        return price >= target
    if alert.condition_type == "below":
        return price <= target
    if alert.condition_type == "change_up":
        return change_percent >= target
    if alert.condition_type == "change_down":
        return change_percent <= -target
    return False


def _cooldown_ok(alert: models.PriceAlert, hours: int = 24) -> bool:
    if not alert.last_triggered_at:
        return True
    now = datetime.now(timezone.utc)
    triggered = alert.last_triggered_at
    if triggered.tzinfo is None:
        triggered = triggered.replace(tzinfo=timezone.utc)
    return now - triggered > timedelta(hours=hours)


def check_price_alerts(db: Session) -> int:
    if not is_configured():
        return 0

    alerts = crud.list_active_alerts(db)
    if not alerts:
        return 0

    tickers = list({a.ticker for a in alerts})
    try:
        quotes = stock_service.get_quotes(tickers)
    except Exception:
        logger.exception("Failed to fetch quotes for alerts")
        return 0

    sent = 0
    for alert in alerts:
        if not _cooldown_ok(alert):
            continue

        quote = quotes.get(alert.ticker)
        if not quote:
            continue

        if not _alert_triggered(alert, quote.price, quote.change_percent):
            continue

        user = crud.get_user(db, alert.user_id)
        if not user or not user.telegram_chat_id:
            continue

        label = CONDITION_LABELS.get(alert.condition_type, alert.condition_type)
        text = (
            f"🔔 <b>Алерт: {alert.ticker}</b>\n"
            f"Условие: {label} {_esc(alert.target_value)}\n"
            f"Сейчас: ${_esc(f'{quote.price:.2f}')} ({quote.change_percent:+.2f}%)"
        )
        if send_message(user.telegram_chat_id, text):
            crud.mark_alert_triggered(db, alert)
            sent += 1
            logger.info("Alert sent for %s user %s", alert.ticker, user.id)

    return sent
