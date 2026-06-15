import json
import logging
import urllib.request

from fastapi import HTTPException, status
from openai import OpenAI
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.schemas import CompanyProfile, MarketContext, PortfolioAnalysis, StockAnalysis, StockQuote
from app.services.market_context import get_market_context
from app.services.stock_service import StockService, stock_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a skeptical professional investment analyst.
Analyze only the supplied data. Do not use general knowledge about the company.
Respond ONLY with valid JSON in Russian language using this schema:
{
  "strengths": ["string"],
  "weaknesses": ["string"],
  "risks": ["string"],
  "investment_conclusion": "string",
  "rating": 1-10 integer
}
Rules:
- Every strength, weakness, and risk must cite a supplied number or a specific missing input.
- Never write generic claims such as "лидер отрасли", "сильная компания", or "имеет потенциал".
- A one-day price move is context, not a buy/sell signal.
- Do not list a positive one-day move as a strength.
- If fewer than two fundamental metrics are available, rating must be 4-6 and confidence is low.
- Rating 1 = strong sell, 10 = strong buy.
- The investment_conclusion must use exactly this practical structure in 4 short sentences:
  1) "Вердикт: <ИЗБЕГАТЬ/НАБЛЮДАТЬ/ОСТОРОЖНО ПОКУПАТЬ/ДЕРЖАТЬ>; уверенность <низкая/средняя/высокая>."
  2) State current price, position in the 52-week range, and distance to its boundaries.
  3) State the main limitation or risk.
  4) State exact supplied price levels that would improve or worsen the view.
- If news or earnings data is supplied, reference specific headlines or report dates; do not invent events.
- If a previous AI rating is supplied, explain whether the new view is stronger, weaker, or unchanged and why.
Never claim certainty, invent missing data, or mention API keys/data-provider setup."""


class AIAnalysisService:
    """AI-powered investment analysis with provider fallbacks."""

    def __init__(
        self,
        stock_svc: StockService | None = None,
        openai_client: OpenAI | None = None,
    ) -> None:
        self.stock_service = stock_svc or stock_service
        self._client = openai_client

    def _get_client(self) -> OpenAI | None:
        if not settings.openai_api_key:
            return None
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=60.0,
                max_retries=2,
            )
        return self._client

    def analyze(
        self,
        ticker: str,
        context: MarketContext | None = None,
        previous_rating: int | None = None,
    ) -> StockAnalysis:
        profile = self.stock_service.get_company_profile(ticker)
        try:
            quote = self.stock_service.get_quote(ticker)
        except Exception as exc:
            logger.warning("Quote context unavailable for %s: %s", ticker, exc)
            quote = None

        if context is None:
            try:
                context = get_market_context(ticker)
            except Exception as exc:
                logger.warning("Market context unavailable for %s: %s", ticker, exc)
                context = MarketContext(ticker=ticker.upper(), news=[], earnings=[])

        prompt = self._build_prompt(profile, quote, context, previous_rating)

        if self._yandex_configured():
            try:
                data = self._call_yandex(prompt, SYSTEM_PROMPT)
                return self._parse_response(profile, data, ai_powered=True, context=context, previous_rating=previous_rating)
            except Exception as exc:
                logger.warning("YandexGPT analysis failed, trying fallback: %s", exc)

        client = self._get_client()
        if client:
            try:
                data = self._call_openai(client, prompt)
                return self._parse_response(profile, data, ai_powered=True, context=context, previous_rating=previous_rating)
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("OpenAI analysis failed, using fallback: %s", exc)

        return self._rule_based_analysis(profile, context, previous_rating)

    def _build_prompt(
        self,
        profile: CompanyProfile,
        quote: StockQuote | None = None,
        context: MarketContext | None = None,
        previous_rating: int | None = None,
    ) -> str:
        f = profile.financials
        market_cap = f"{f.market_cap:,.0f}" if f.market_cap else "N/A"
        pe = f"{f.pe_ratio:.2f}" if f.pe_ratio is not None else "N/A"
        eps = f"{f.eps:.2f}" if f.eps is not None else "N/A"
        growth = f"{f.revenue_growth:.2f}%" if f.revenue_growth is not None else "N/A"
        available_fundamentals = sum(
            value is not None
            for value in (f.market_cap, f.pe_ratio, f.eps, f.revenue_growth)
        )
        daily_change = f"{quote.change_percent:+.2f}%" if quote else "N/A"
        year_range = "N/A"
        range_position = "N/A"
        range_context = "Недоступен"
        if quote and quote.fifty_two_week_low is not None and quote.fifty_two_week_high is not None:
            low = quote.fifty_two_week_low
            high = quote.fifty_two_week_high
            year_range = f"{low:.2f}–{high:.2f} {quote.currency}"
            if high > low:
                position = (quote.price - low) / (high - low) * 100
                range_position = f"{position:.1f}% от минимума к максимуму"
                distance_to_high = (high - quote.price) / quote.price * 100
                distance_from_low = (quote.price - low) / quote.price * 100
                if position >= 75:
                    zone = "верхняя четверть диапазона: не догонять цену без новых данных"
                elif position <= 25:
                    zone = "нижняя четверть диапазона: нужен признак стабилизации"
                else:
                    zone = "середина диапазона: выраженного ценового преимущества нет"
                range_context = (
                    f"{zone}; до максимума {distance_to_high:.1f}%, "
                    f"выше минимума на {distance_from_low:.1f}%; "
                    f"контрольные уровни: ухудшение ниже {low:.2f}, "
                    f"улучшение выше {high:.2f} {quote.currency}"
                )

        news_block = "Нет свежих новостей в данных."
        earnings_block = "Нет данных по отчётности."
        if context:
            if context.news:
                lines = []
                for item in context.news[:5]:
                    dt = item.published_at.strftime("%Y-%m-%d")
                    lines.append(f"- [{dt}] {item.headline} ({item.source})")
                    if item.summary:
                        lines.append(f"  {item.summary[:200]}")
                news_block = "\n".join(lines)
            if context.earnings:
                elines = []
                for evt in context.earnings[:3]:
                    parts = [evt.date]
                    if evt.period:
                        parts.append(f"period {evt.period}")
                    if evt.eps_actual is not None:
                        parts.append(f"EPS fact {evt.eps_actual}")
                    if evt.eps_estimate is not None:
                        parts.append(f"EPS est {evt.eps_estimate}")
                    if evt.surprise_pct is not None:
                        parts.append(f"surprise {evt.surprise_pct:+.1f}%")
                    elines.append("- " + ", ".join(parts))
                earnings_block = "\n".join(elines)
            if context.upcoming_earnings:
                ue = context.upcoming_earnings
                earnings_block += f"\n- Ближайший отчёт: {ue.date}"
                if ue.eps_estimate is not None:
                    earnings_block += f", EPS consensus {ue.eps_estimate}"

        prev_rating_line = (
            f"Предыдущий AI-рейтинг по этому тикеру: {previous_rating}/10"
            if previous_rating is not None
            else "Предыдущий AI-рейтинг: нет данных"
        )

        return f"""Проанализируй акцию для частного инвестора.

Тикер: {profile.ticker}
Компания: {profile.name}
Сектор: {profile.sector or "N/A"}
Отрасль: {profile.industry or "N/A"}

Финансовые данные:
- Текущая цена: {f.current_price} {f.currency}
- Рыночная капитализация: {market_cap}
- P/E: {pe}
- EPS: {eps}
- Рост выручки (YoY): {growth}
- Изменение за последнюю сессию: {daily_change}
- Диапазон за 52 недели: {year_range}
- Положение цены внутри диапазона: {range_position}
- Интерпретация диапазона и контрольные уровни: {range_context}
- Доступно фундаментальных метрик: {available_fundamentals} из 4
- {prev_rating_line}

Последние новости:
{news_block}

Отчётность / earnings:
{earnings_block}

Описание компании:
{profile.description}

Отделяй наблюдаемые данные от предположений. Если фундаментальных метрик меньше двух,
не оценивай качество бизнеса и не предлагай уверенную покупку или продажу.
Учитывай новости и earnings только если они перечислены выше.
"""

    def _call_openai(self, client: OpenAI, prompt: str) -> dict:
        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.exception("Invalid JSON from OpenAI")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid response from OpenAI",
            ) from exc

    @staticmethod
    def _yandex_configured() -> bool:
        return bool(settings.yandex_cloud_api_key and settings.yandex_cloud_folder_id)

    def _call_yandex(self, prompt: str, system_prompt: str) -> dict:
        body = {
            "modelUri": (
                f"gpt://{settings.yandex_cloud_folder_id}/{settings.yandex_gpt_model}"
            ),
            "completionOptions": {
                "stream": False,
                "temperature": 0.45,
                "maxTokens": 2000,
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": prompt},
            ],
        }
        request = urllib.request.Request(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Api-Key {settings.yandex_cloud_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)

        content = payload["result"]["alternatives"][0]["message"]["text"].strip()
        if content.startswith("```"):
            content = content.removeprefix("```json").removeprefix("```")
            content = content.removesuffix("```").strip()
        return json.loads(content)

    def _rule_based_analysis(
        self,
        profile: CompanyProfile,
        context: MarketContext | None = None,
        previous_rating: int | None = None,
    ) -> StockAnalysis:
        f = profile.financials
        strengths: list[str] = []
        weaknesses: list[str] = []
        risks: list[str] = []

        if f.revenue_growth is not None:
            if f.revenue_growth > 10:
                strengths.append(f"Высокий рост выручки: {f.revenue_growth:.1f}% YoY")
            elif f.revenue_growth < 0:
                weaknesses.append(f"Падение выручки: {f.revenue_growth:.1f}% YoY")

        if f.pe_ratio is not None:
            if f.pe_ratio < 15:
                strengths.append(f"Низкий P/E ({f.pe_ratio:.1f}) — возможная недооценка")
            elif f.pe_ratio > 35:
                weaknesses.append(f"Высокий P/E ({f.pe_ratio:.1f}) — премия к рынку")
                risks.append("Завышенные ожидания рынка относительно прибыли")

        if f.eps is not None and f.eps > 0:
            strengths.append(f"Положительный EPS: ${f.eps:.2f}")

        if profile.sector:
            strengths.append(f"Сектор: {profile.sector}")

        if context and context.upcoming_earnings:
            ue = context.upcoming_earnings
            risks.append(f"Ближайший earnings {ue.date} — возможна повышенная волатильность")
        if context and context.news:
            risks.append(f"На фоне {len(context.news)} свежих новостей — следите за sentiment")

        if not strengths:
            strengths.append(f"Цена ${f.current_price:.2f} доступна, но фундаментальные метрики отсутствуют")
        if not weaknesses:
            weaknesses.append("Недостаточно фундаментальных метрик для оценки качества бизнеса")
        if not risks:
            risks.append("Рыночная волатильность и макроэкономические факторы")

        rating = 5
        if f.pe_ratio is not None:
            if f.pe_ratio < 20 and (f.revenue_growth or 0) > 5:
                rating = 7
            elif f.pe_ratio > 40:
                rating = 4

        growth = f.revenue_growth
        if rating >= 7:
            stance = "Акцию можно рассматривать для осторожного набора позиции частями"
        elif rating <= 4:
            stance = "С покупкой лучше не спешить и дождаться улучшения показателей или оценки"
        else:
            stance = "Разумная стратегия — наблюдать за акцией и входить только при подходящей цене"

        evidence: list[str] = []
        if growth is not None:
            direction = "растёт" if growth > 0 else "снижается"
            evidence.append(f"выручка {direction} на {abs(growth):.1f}% год к году")
        if f.pe_ratio is not None:
            evidence.append(f"P/E составляет {f.pe_ratio:.1f}")
        if f.eps is not None:
            evidence.append(f"EPS составляет ${f.eps:.2f}")

        evidence_text = (
            "Ключевые доступные показатели: " + ", ".join(evidence) + "."
            if evidence
            else "Доступных фундаментальных показателей недостаточно для уверенной оценки."
        )
        main_risk = risks[0].rstrip(".")
        conclusion = (
            f"Вердикт: НАБЛЮДАТЬ; уверенность низкая. "
            f"{evidence_text} "
            f"Главный риск: {main_risk.lower()}. "
            f"Оценка улучшится после появления свежих данных по выручке, прибыли и P/E; "
            f"до этого {stance.lower()}."
        )

        return StockAnalysis(
            ticker=profile.ticker,
            name=profile.name,
            current_price=f.current_price,
            currency=f.currency,
            strengths=strengths,
            weaknesses=weaknesses,
            risks=risks,
            investment_conclusion=conclusion,
            rating=rating,
            ai_powered=False,
            news=context.news if context else [],
            earnings=context.earnings if context else [],
            upcoming_earnings=context.upcoming_earnings if context else None,
            previous_rating=previous_rating,
        )

    def _parse_response(
        self,
        profile: CompanyProfile,
        data: dict,
        ai_powered: bool,
        context: MarketContext | None = None,
        previous_rating: int | None = None,
    ) -> StockAnalysis:
        rating = data.get("rating", 5)
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            rating = 5
        rating = max(1, min(10, rating))

        return StockAnalysis(
            ticker=profile.ticker,
            name=profile.name,
            current_price=profile.financials.current_price,
            currency=profile.financials.currency,
            strengths=self._as_list(data.get("strengths")),
            weaknesses=self._as_list(data.get("weaknesses")),
            risks=self._as_list(data.get("risks")),
            investment_conclusion=str(data.get("investment_conclusion") or ""),
            rating=rating,
            ai_powered=ai_powered,
            news=context.news if context else [],
            earnings=context.earnings if context else [],
            upcoming_earnings=context.upcoming_earnings if context else None,
            previous_rating=previous_rating,
        )

    @staticmethod
    def _as_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]

    def analyze_portfolio(self, db: Session, user_id: int) -> PortfolioAnalysis:
        holdings = crud.list_holdings(db, user_id)
        if not holdings:
            raise HTTPException(status_code=400, detail="Portfolio is empty")

        tickers = [h.ticker for h in holdings]
        quotes = self.stock_service.get_quotes(tickers)
        total_cost, total_value = crud.portfolio_totals(holdings, {t: q.price for t, q in quotes.items()})
        total_pnl_pct = ((total_value - total_cost) / total_cost * 100) if total_cost else 0

        lines = []
        for h in holdings:
            q = quotes.get(h.ticker)
            price = q.price if q else float(h.avg_price)
            shares = float(h.shares)
            value = shares * price
            cost = shares * float(h.avg_price)
            pnl = value - cost
            lines.append(
                f"- {h.ticker}: {shares:g} шт., avg ${float(h.avg_price):.2f}, "
                f"now ${price:.2f}, value ${value:.2f}, P/L ${pnl:.2f}"
            )

        portfolio_text = "\n".join(lines)
        prompt = (
            "Проанализируй инвестиционный портфель частного инвестора.\n\n"
            f"Позиции:\n{portfolio_text}\n\n"
            f"Итого: ${total_value:.2f} (инвестировано ${total_cost:.2f}, P/L {total_pnl_pct:+.1f}%)\n\n"
            "Дай оценку диверсификации, рисков и общую рекомендацию."
        )

        portfolio_system_prompt = (
            "You are a portfolio analyst. Respond ONLY with valid JSON in Russian: "
            "summary, strengths[], weaknesses[], risks[], recommendation, rating (1-10)."
        )
        data = None
        if self._yandex_configured():
            try:
                data = self._call_yandex(prompt, portfolio_system_prompt)
            except Exception as exc:
                logger.warning("YandexGPT portfolio analysis failed: %s", exc)

        client = self._get_client()
        if data is None and client:
            try:
                response = client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": portfolio_system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )
                data = json.loads(response.choices[0].message.content or "{}")
            except Exception as exc:
                logger.warning("OpenAI portfolio analysis failed: %s", exc)

        if data is not None:
            try:
                rating = max(1, min(10, int(data.get("rating", 5))))
                return PortfolioAnalysis(
                    summary=str(data.get("summary", "")),
                    strengths=self._as_list(data.get("strengths")),
                    weaknesses=self._as_list(data.get("weaknesses")),
                    risks=self._as_list(data.get("risks")),
                    recommendation=str(data.get("recommendation", "")),
                    rating=rating,
                    ai_powered=True,
                    holdings_count=len(holdings),
                    tickers=tickers,
                )
            except Exception as exc:
                logger.warning("Invalid portfolio AI response: %s", exc)

        return PortfolioAnalysis(
            summary=f"Портфель из {len(holdings)} позиций на сумму ${total_value:.2f} (P/L {total_pnl_pct:+.1f}%).",
            strengths=[f"Диверсификация: {len(tickers)} тикеров"] if len(tickers) > 1 else ["Компактный портфель"],
            weaknesses=["Недостаточно данных для глубокого AI-анализа"],
            risks=["Концентрация в отдельных позициях"] if len(tickers) < 3 else ["Рыночная волатильность"],
            recommendation="Держать и ребалансировать при необходимости",
            rating=6 if total_pnl_pct >= 0 else 4,
            ai_powered=False,
            holdings_count=len(holdings),
            tickers=tickers,
        )


ai_analysis_service = AIAnalysisService()
