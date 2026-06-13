import json
import logging

from openai import OpenAI

from app.config import settings
from app.schemas import StockAnalysis, StockQuote

logger = logging.getLogger(__name__)


def _rule_based_analysis(quote: StockQuote) -> StockAnalysis:
    strengths: list[str] = []
    risks: list[str] = []

    if quote.change_percent > 0:
        strengths.append(f"Акция растёт сегодня на {quote.change_percent:.2f}%")
    elif quote.change_percent < 0:
        risks.append(f"Сегодня падение на {abs(quote.change_percent):.2f}%")

    if quote.pe_ratio is not None:
        if quote.pe_ratio < 15:
            strengths.append(f"Низкий P/E ({quote.pe_ratio:.1f}) — возможная недооценка")
        elif quote.pe_ratio > 35:
            risks.append(f"Высокий P/E ({quote.pe_ratio:.1f}) — премия к рынку")

    if quote.fifty_two_week_high and quote.fifty_two_week_low:
        range_position = (quote.price - quote.fifty_two_week_low) / (
            quote.fifty_two_week_high - quote.fifty_two_week_low
        )
        if range_position > 0.85:
            risks.append("Цена близка к 52-недельному максимуму")
        elif range_position < 0.25:
            strengths.append("Цена близка к 52-недельному минимуму")

    if quote.sector:
        strengths.append(f"Сектор: {quote.sector}")

    if not strengths:
        strengths.append("Стабильные рыночные данные доступны для анализа")
    if not risks:
        risks.append("Рыночная волатильность может повлиять на краткосрочную динамику")

    if quote.change_percent >= 2:
        recommendation = "Наблюдать — позитивный импульс"
    elif quote.change_percent <= -2:
        recommendation = "Осторожно — негативный импульс"
    else:
        recommendation = "Держать — нейтральная динамика"

    summary = (
        f"{quote.name} ({quote.ticker}) торгуется по ${quote.price:.2f} "
        f"({quote.change_percent:+.2f}% за день). "
        f"Анализ основан на публичных рыночных данных."
    )

    return StockAnalysis(
        ticker=quote.ticker,
        quote=quote,
        summary=summary,
        strengths=strengths,
        risks=risks,
        recommendation=recommendation,
        ai_powered=False,
    )


def _openai_analysis(quote: StockQuote) -> StockAnalysis:
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""Analyze this stock for a retail investor. Respond in Russian as JSON with keys:
summary (string), strengths (array of strings), risks (array of strings), recommendation (string).

Stock: {quote.ticker} - {quote.name}
Price: ${quote.price} ({quote.change_percent:+.2f}% today)
P/E: {quote.pe_ratio}
52w range: {quote.fifty_two_week_low} - {quote.fifty_two_week_high}
Sector: {quote.sector}
Industry: {quote.industry}
"""
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "You are a professional investment analyst. Be concise and factual.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    content = response.choices[0].message.content or "{}"
    data = json.loads(content)
    return StockAnalysis(
        ticker=quote.ticker,
        quote=quote,
        summary=data.get("summary", ""),
        strengths=data.get("strengths", []),
        risks=data.get("risks", []),
        recommendation=data.get("recommendation", "Hold"),
        ai_powered=True,
    )


def analyze_stock(quote: StockQuote) -> StockAnalysis:
    if settings.openai_api_key:
        try:
            return _openai_analysis(quote)
        except Exception as exc:
            logger.warning("OpenAI analysis failed, falling back: %s", exc)
    return _rule_based_analysis(quote)
