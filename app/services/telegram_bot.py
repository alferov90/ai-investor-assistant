import html
import logging
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.services.ai_analysis import ai_analysis_service
from app.services.portfolio_digest import build_portfolio_digest
from app.services.stock_service import stock_service
from app.telegram_client import send_message

logger = logging.getLogger("ai-investor.telegram")

_CONDITION_LABELS = {
    "above": "цена выше",
    "below": "цена ниже",
    "change_up": "рост за день ≥",
    "change_down": "падение за день ≥",
}

_HELP_TEXT = (
    "👋 <b>AI Investor Assistant</b>\n\n"
    "<b>Анализ</b>\n"
    "/analyze NVDA — AI-анализ акции\n\n"
    "<b>Портфель</b>\n"
    "/portfolio — позиции и P/L\n"
    "/digest — дайджест портфеля сейчас\n\n"
    "<b>Watchlist</b>\n"
    "/watchlist — список\n"
    "/watchadd AAPL — добавить\n"
    "/watchdel AAPL — удалить\n\n"
    "<b>Алерты</b>\n"
    "/alerts — список\n"
    "/alert AAPL above 150 — создать\n"
    "/alertdel 3 — удалить по ID\n\n"
    "Подключение: Dashboard → Telegram → «Подключить»"
)


def _esc(text: str) -> str:
    return html.escape(str(text))


def _format_list(title: str, items: list[str], limit: int = 5) -> str:
    if not items:
        return f"<b>{title}</b>\n—"
    lines = [f"<b>{title}</b>"]
    for item in items[:limit]:
        lines.append(f"• {_esc(item)}")
    return "\n".join(lines)


class TelegramBotService:
    """Telegram bot handlers integrated with the same services as FastAPI API."""

    def _require_user(self, db: Session, chat_id: int):
        user = crud.get_user_by_telegram_chat_id(db, chat_id)
        if not user:
            send_message(
                chat_id,
                "🔒 Команда доступна после подключения аккаунта.\n"
                "Dashboard → Telegram → «Подключить»",
            )
        return user

    def handle_start(self, db: Session, chat_id: int, args: list[str]) -> None:
        if args:
            token = args[0]
            user = crud.get_user_by_link_token(db, token)
            if not user:
                send_message(chat_id, "❌ Ссылка устарела. Создайте новую в Dashboard.")
                return
            crud.link_telegram(db, user, chat_id)
            send_message(
                chat_id,
                f"✅ Аккаунт подключён, <b>{_esc(user.name)}</b>!\n\n{_HELP_TEXT}",
            )
            logger.info("Telegram linked for user %s", user.id)
            return

        send_message(chat_id, _HELP_TEXT)

    def handle_help(self, chat_id: int) -> None:
        send_message(chat_id, _HELP_TEXT)

    def handle_analyze(self, db: Session, chat_id: int, args: list[str]) -> None:
        if not args:
            send_message(
                chat_id,
                "Использование: <code>/analyze NVDA</code>\n"
                "Примеры: /analyze NVDA, /analyze AAPL",
            )
            return

        ticker = args[0].upper()
        send_message(chat_id, f"⏳ Анализирую <b>{_esc(ticker)}</b>...")

        try:
            analysis = ai_analysis_service.analyze(ticker)
            user = crud.get_user_by_telegram_chat_id(db, chat_id)
            if user:
                crud.save_analysis(db, user.id, analysis)
        except HTTPException as exc:
            send_message(chat_id, f"❌ {_esc(str(exc.detail))}")
            return
        except Exception:
            logger.exception("Telegram analyze failed for %s", ticker)
            send_message(chat_id, "❌ Не удалось выполнить анализ. Попробуйте позже.")
            return

        text = (
            f"📊 <b>{_esc(analysis.ticker)}</b> — {_esc(analysis.name)}\n"
            f"💰 {_esc(f'${analysis.current_price:.2f}')}\n"
            f"⭐ Рейтинг: <b>{analysis.rating}/10</b>"
            f"{' (GPT)' if analysis.ai_powered else ' (базовый)'}\n\n"
            f"{_format_list('✅ Сильные стороны', analysis.strengths)}\n\n"
            f"{_format_list('⚠️ Слабые стороны', analysis.weaknesses)}\n\n"
            f"{_format_list('🔴 Риски', analysis.risks)}\n\n"
            f"<b>📝 Инвестиционный вывод</b>\n{_esc(analysis.investment_conclusion)}"
        )
        send_message(chat_id, text)

    def handle_portfolio(self, db: Session, chat_id: int) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        holdings = crud.list_holdings(db, user.id)
        if not holdings:
            send_message(chat_id, "📁 Портфель пуст.\nДобавьте тикеры на сайте: /portfolio")
            return

        tickers = [h.ticker for h in holdings]
        quotes = stock_service.get_quotes(tickers)
        prices = {t: q.price for t, q in quotes.items()}

        total_cost, total_value = crud.portfolio_totals(holdings, prices)
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

        lines = [f"📁 <b>Портфель {_esc(user.name)}</b>\n"]
        for holding in holdings:
            shares = float(holding.shares)
            avg_price = float(holding.avg_price)
            price = prices.get(holding.ticker, avg_price)
            value = shares * price
            cost = shares * avg_price
            pnl = value - cost
            pnl_pct = (pnl / cost * 100) if cost else 0
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"\n<b>{_esc(holding.ticker)}</b> — {shares:g} шт. × ${avg_price:.2f}\n"
                f"  Текущая: ${price:.2f} | P/L: {sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%)"
            )

        sign = "+" if total_pnl >= 0 else ""
        lines.append(
            f"\n<b>Итого:</b> ${total_value:.2f}\n"
            f"<b>P/L:</b> {sign}${total_pnl:.2f} ({sign}{total_pnl_pct:.1f}%)"
        )
        send_message(chat_id, "\n".join(lines))

    def handle_digest(self, db: Session, chat_id: int) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        text = build_portfolio_digest(db, user)
        if not text:
            send_message(chat_id, "📁 Портфель пуст — дайджест нечего отправлять.")
            return
        send_message(chat_id, text)

    def handle_watchlist(self, db: Session, chat_id: int) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        items = crud.list_watchlist(db, user.id)
        if not items:
            send_message(chat_id, "👁 Watchlist пуст.\nДобавьте: <code>/watchadd AAPL</code>")
            return

        tickers = [i.ticker for i in items]
        quotes = stock_service.get_quotes(tickers)
        lines = [f"👁 <b>Watchlist</b> ({len(items)})\n"]
        for item in items:
            q = quotes.get(item.ticker)
            if q:
                lines.append(
                    f"• <b>{_esc(item.ticker)}</b> ${q.price:.2f} ({q.change_percent:+.1f}%)"
                )
            else:
                lines.append(f"• <b>{_esc(item.ticker)}</b> — нет данных")
        lines.append("\n/watchadd TICKER · /watchdel TICKER")
        send_message(chat_id, "\n".join(lines))

    def handle_watchadd(self, db: Session, chat_id: int, args: list[str]) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        if not args:
            send_message(chat_id, "Использование: <code>/watchadd AAPL</code>")
            return

        ticker = args[0].upper()
        if crud.get_watchlist_by_ticker(db, user.id, ticker):
            send_message(chat_id, f"ℹ️ <b>{_esc(ticker)}</b> уже в watchlist.")
            return

        try:
            crud.create_watchlist_item(db, user.id, schemas.WatchlistCreate(ticker=ticker))
        except Exception:
            send_message(chat_id, f"❌ Не удалось добавить {_esc(ticker)}.")
            return

        send_message(chat_id, f"✅ <b>{_esc(ticker)}</b> добавлен в watchlist.")

    def handle_watchdel(self, db: Session, chat_id: int, args: list[str]) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        if not args:
            send_message(chat_id, "Использование: <code>/watchdel AAPL</code>")
            return

        ticker = args[0].upper()
        if crud.delete_watchlist_by_ticker(db, user.id, ticker):
            send_message(chat_id, f"🗑 <b>{_esc(ticker)}</b> удалён из watchlist.")
        else:
            send_message(chat_id, f"❌ <b>{_esc(ticker)}</b> не найден в watchlist.")

    def handle_alerts(self, db: Session, chat_id: int) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        alerts = crud.list_alerts(db, user.id)
        if not alerts:
            send_message(
                chat_id,
                "🔔 Алертов нет.\n"
                "Создать: <code>/alert AAPL above 150</code>",
            )
            return

        lines = [f"🔔 <b>Алерты</b> ({len(alerts)})\n"]
        for alert in alerts[:15]:
            label = _CONDITION_LABELS.get(alert.condition_type, alert.condition_type)
            status = "✅" if alert.is_active else "⏸"
            lines.append(
                f"{status} #{alert.id} <b>{_esc(alert.ticker)}</b> — {label} "
                f"{float(alert.target_value):g}"
            )
        lines.append(
            "\n/alert TICKER above|below|change_up|change_down VALUE\n"
            "/alertdel ID"
        )
        send_message(chat_id, "\n".join(lines))

    def handle_alert(self, db: Session, chat_id: int, args: list[str]) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        if len(args) < 3:
            send_message(
                chat_id,
                "Использование:\n"
                "<code>/alert AAPL above 150</code>\n"
                "<code>/alert NVDA below 100</code>\n"
                "<code>/alert TSLA change_up 5</code>\n"
                "<code>/alert AAPL change_down 3</code>",
            )
            return

        ticker = args[0].upper()
        condition = args[1].lower()
        try:
            target = Decimal(args[2])
        except Exception:
            send_message(chat_id, "❌ Неверное значение. Пример: <code>/alert AAPL above 150</code>")
            return

        try:
            alert = crud.create_alert(
                db,
                user.id,
                schemas.AlertCreate(
                    ticker=ticker,
                    condition_type=condition,
                    target_value=target,
                ),
            )
        except Exception as exc:
            send_message(chat_id, f"❌ {_esc(str(exc))}")
            return

        label = _CONDITION_LABELS.get(alert.condition_type, alert.condition_type)
        send_message(
            chat_id,
            f"✅ Алерт #{alert.id}: <b>{_esc(ticker)}</b> — {label} {float(target):g}",
        )

    def handle_alertdel(self, db: Session, chat_id: int, args: list[str]) -> None:
        user = self._require_user(db, chat_id)
        if not user:
            return

        if not args:
            send_message(chat_id, "Использование: <code>/alertdel 3</code>")
            return

        try:
            alert_id = int(args[0])
        except ValueError:
            send_message(chat_id, "❌ Укажите ID алерта. Список: /alerts")
            return

        alert = crud.get_alert(db, user.id, alert_id)
        if not alert:
            send_message(chat_id, f"❌ Алерт #{alert_id} не найден.")
            return

        crud.delete_alert(db, alert)
        send_message(chat_id, f"🗑 Алерт #{alert_id} удалён.")

    def handle_message(self, db: Session, chat_id: int, text: str) -> None:
        parts = text.split()
        command = parts[0].split("@")[0].lower()
        args = parts[1:]

        handlers = {
            "/start": lambda: self.handle_start(db, chat_id, args),
            "/help": lambda: self.handle_help(chat_id),
            "/analyze": lambda: self.handle_analyze(db, chat_id, args),
            "/portfolio": lambda: self.handle_portfolio(db, chat_id),
            "/digest": lambda: self.handle_digest(db, chat_id),
            "/watchlist": lambda: self.handle_watchlist(db, chat_id),
            "/watchadd": lambda: self.handle_watchadd(db, chat_id, args),
            "/watchdel": lambda: self.handle_watchdel(db, chat_id, args),
            "/alerts": lambda: self.handle_alerts(db, chat_id),
            "/alert": lambda: self.handle_alert(db, chat_id, args),
            "/alertdel": lambda: self.handle_alertdel(db, chat_id, args),
        }

        handler = handlers.get(command)
        if handler:
            handler()
        else:
            send_message(chat_id, f"Неизвестная команда.\n\n{_HELP_TEXT}")


telegram_bot_service = TelegramBotService()
