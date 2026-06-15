import json
import logging

from fastapi import HTTPException, status
from openai import OpenAI
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.schemas import CompanyProfile, PortfolioAnalysis, StockAnalysis
from app.services.stock_service import StockService, stock_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional investment analyst.
Analyze stocks based on financial data and company description.
Respond ONLY with valid JSON in Russian language using this schema:
{
  "strengths": ["string"],
  "weaknesses": ["string"],
  "risks": ["string"],
  "investment_conclusion": "string",
  "rating": 1-10 integer
}
Be factual, concise, and balanced. Rating 1 = strong sell, 10 = strong buy."""


class AIAnalysisService:
    """OpenAI-powered investment analysis for stocks."""

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

    def analyze(self, ticker: str) -> StockAnalysis:
        profile = self.stock_service.get_company_profile(ticker)

        client = self._get_client()
        if client:
            try:
                prompt = self._build_prompt(profile)
                data = self._call_openai(client, prompt)
                return self._parse_response(profile, data, ai_powered=True)
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("OpenAI analysis failed, using fallback: %s", exc)

        return self._rule_based_analysis(profile)

    def _build_prompt(self, profile: CompanyProfile) -> str:
        f = profile.financials
        market_cap = f"{f.market_cap:,.0f}" if f.market_cap else "N/A"
        pe = f"{f.pe_ratio:.2f}" if f.pe_ratio is not None else "N/A"
        eps = f"{f.eps:.2f}" if f.eps is not None else "N/A"
        growth = f"{f.revenue_growth:.2f}%" if f.revenue_growth is not None else "N/A"

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

Описание компании:
{profile.description}
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

    def _rule_based_analysis(self, profile: CompanyProfile) -> StockAnalysis:
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

        if not strengths:
            strengths.append("Доступны актуальные рыночные и финансовые данные")
        if not weaknesses:
            weaknesses.append("Ограниченная глубина анализа без OpenAI")
        if not risks:
            risks.append("Рыночная волатильность и макроэкономические факторы")

        rating = 5
        if f.pe_ratio is not None:
            if f.pe_ratio < 20 and (f.revenue_growth or 0) > 5:
                rating = 7
            elif f.pe_ratio > 40:
                rating = 4

        conclusion = (
            f"{profile.name} ({profile.ticker}) торгуется по ${f.current_price:.2f}. "
            f"Базовый анализ на основе Yahoo Finance. "
            f"Для GPT-анализа добавьте OPENAI_API_KEY на сервере."
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
        )

    def _parse_response(
        self, profile: CompanyProfile, data: dict, ai_powered: bool
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

        client = self._get_client()
        if client:
            try:
                response = client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a portfolio analyst. Respond in Russian as JSON: "
                                "summary, strengths[], weaknesses[], risks[], recommendation, rating (1-10)."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )
                data = json.loads(response.choices[0].message.content or "{}")
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
                logger.warning("Portfolio AI analysis failed: %s", exc)

        return PortfolioAnalysis(
            summary=f"Портфель из {len(holdings)} позиций на сумму ${total_value:.2f} (P/L {total_pnl_pct:+.1f}%).",
            strengths=[f"Диверсификация: {len(tickers)} тикеров"] if len(tickers) > 1 else ["Компактный портфель"],
            weaknesses=["Добавьте OPENAI_API_KEY для глубокого AI-анализа"],
            risks=["Концентрация в отдельных позициях"] if len(tickers) < 3 else ["Рыночная волатильность"],
            recommendation="Держать и ребалансировать при необходимости",
            rating=6 if total_pnl_pct >= 0 else 4,
            ai_powered=False,
            holdings_count=len(holdings),
            tickers=tickers,
        )


ai_analysis_service = AIAnalysisService()
