import html
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.services.ai_analysis import ai_analysis_service
from app.services.stock_service import stock_service
from app.telegram_client import send_message

logger = logging.getLogger("ai-investor.telegram")


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
                f"✅ Аккаунт подключён, <b>{_esc(user.name)}</b>!\n\n"
                "Доступные команды:\n"
                "/analyze NVDA — AI-анализ\n"
                "/analyze AAPL — AI-анализ Apple\n"
                "/portfolio — ваш портфель",
            )
            logger.info("Telegram linked for user %s", user.id)
            return

        send_message(
            chat_id,
            "👋 <b>AI Investor Assistant</b>\n\n"
            "Команды:\n"
            "/analyze NVDA — AI-анализ NVIDIA\n"
            "/analyze AAPL — AI-анализ Apple\n"
            "/portfolio — ваш портфель\n\n"
            "Для доступа к портфелю подключите аккаунт:\n"
            "Dashboard → Telegram → «Подключить»",
        )

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
        user = crud.get_user_by_telegram_chat_id(db, chat_id)
        if not user:
            send_message(
                chat_id,
                "🔒 Портфель доступен после подключения аккаунта.\n"
                "Откройте Dashboard → Telegram → «Подключить».",
            )
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

    def handle_message(self, db: Session, chat_id: int, text: str) -> None:
        parts = text.split()
        command = parts[0].split("@")[0].lower()
        args = parts[1:]

        if command == "/start":
            self.handle_start(db, chat_id, args)
        elif command == "/analyze":
            self.handle_analyze(db, chat_id, args)
        elif command == "/portfolio":
            self.handle_portfolio(db, chat_id)
        else:
            send_message(
                chat_id,
                "Неизвестная команда.\n\n"
                "/start — помощь\n"
                "/analyze NVDA — AI-анализ\n"
                "/portfolio — портфель",
            )


telegram_bot_service = TelegramBotService()
