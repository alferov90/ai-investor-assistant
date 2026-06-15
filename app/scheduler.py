import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal
from app.services.alert_checker import check_price_alerts
from app.services.portfolio_digest import send_morning_digests
from app.services.telegram_bot import telegram_bot_service
from app.telegram_client import delete_webhook, get_updates, is_configured, set_bot_commands

logger = logging.getLogger("ai-investor")

_scheduler: BackgroundScheduler | None = None
_telegram_offset: int | None = None


def poll_telegram() -> None:
    global _telegram_offset
    if not is_configured():
        return

    updates = get_updates(_telegram_offset)
    if not updates:
        return

    db = SessionLocal()
    try:
        for update in updates:
            _telegram_offset = update["update_id"] + 1
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if not chat_id or not text.startswith("/"):
                continue
            telegram_bot_service.handle_message(db, chat_id, text)
    except Exception:
        logger.exception("Telegram polling failed")
    finally:
        db.close()


def run_alert_checks() -> None:
    db = SessionLocal()
    try:
        count = check_price_alerts(db)
        if count:
            logger.info("Sent %s price alert(s)", count)
    except Exception:
        logger.exception("Alert check failed")
    finally:
        db.close()


def run_morning_digest() -> None:
    db = SessionLocal()
    try:
        count = send_morning_digests(db)
        if count:
            logger.info("Sent %s morning digest(s)", count)
    except Exception:
        logger.exception("Morning digest failed")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler()
    if is_configured():
        delete_webhook()
        set_bot_commands()
        _scheduler.add_job(
            poll_telegram,
            "interval",
            seconds=3,
            id="telegram",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=5,
            next_run_time=datetime.now(),
        )
        logger.info("Telegram bot polling started (@%s)", settings.telegram_bot_username)
    else:
        logger.info("Telegram bot not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME)")

    _scheduler.add_job(
        run_alert_checks,
        "interval",
        minutes=5,
        id="alerts",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
        next_run_time=datetime.now(),
    )
    logger.info("Price alert checker started (every 5 min)")

    if is_configured():
        _scheduler.add_job(
            run_morning_digest,
            "cron",
            hour=settings.telegram_digest_hour,
            minute=settings.telegram_digest_minute,
            id="digest",
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "Morning digest scheduled at %02d:%02d UTC",
            settings.telegram_digest_hour,
            settings.telegram_digest_minute,
        )

    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
