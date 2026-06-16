from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    is_active: bool
    created_at: datetime
    telegram_connected: bool = False


class TelegramStatus(BaseModel):
    configured: bool
    connected: bool
    bot_username: str | None = None


class TelegramLink(BaseModel):
    link: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PortfolioHoldingCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    shares: Decimal = Field(gt=0)
    avg_price: Decimal = Field(ge=0)
    notes: str = Field(default="", max_length=500)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioHoldingUpdate(BaseModel):
    shares: Decimal | None = Field(default=None, gt=0)
    avg_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class PortfolioHoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    shares: Decimal
    avg_price: Decimal
    notes: str
    created_at: datetime
    updated_at: datetime


class StockDetail(BaseModel):
    ticker: str
    name: str
    currency: str = "USD"
    current_price: float
    market_cap: float | None = None
    pe_ratio: float | None = None
    eps: float | None = None
    revenue_growth: float | None = None


class StockQuote(BaseModel):
    ticker: str
    name: str
    price: float
    change: float
    change_percent: float
    currency: str = "USD"
    market: str = "us"
    market_cap: float | None = None
    pe_ratio: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    sector: str | None = None
    industry: str | None = None


class CompanyProfile(BaseModel):
    ticker: str
    name: str
    description: str
    sector: str | None = None
    industry: str | None = None
    financials: StockDetail


class StockAnalysis(BaseModel):
    ticker: str
    name: str
    current_price: float
    currency: str = "USD"
    strengths: list[str]
    weaknesses: list[str]
    risks: list[str]
    investment_conclusion: str
    rating: int = Field(ge=1, le=10)
    ai_powered: bool = True
    news: list["NewsItem"] = []
    earnings: list["EarningsEvent"] = []
    upcoming_earnings: "EarningsEvent | None" = None
    previous_rating: int | None = None


class NewsItem(BaseModel):
    headline: str
    summary: str = ""
    headline_ru: str | None = None
    summary_ru: str | None = None
    source: str = ""
    published_at: datetime
    url: str | None = None


class EarningsEvent(BaseModel):
    date: str
    period: str | None = None
    eps_actual: float | None = None
    eps_estimate: float | None = None
    revenue_actual: float | None = None
    revenue_estimate: float | None = None
    surprise_pct: float | None = None


class MarketContext(BaseModel):
    ticker: str
    news: list[NewsItem]
    earnings: list[EarningsEvent]
    upcoming_earnings: EarningsEvent | None = None


class TransactionCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    txn_type: str
    shares: Decimal = Field(ge=0)
    price: Decimal = Field(ge=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    traded_at: datetime
    notes: str = Field(default="", max_length=500)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("txn_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        val = value.strip().lower()
        if val not in {"buy", "sell", "dividend"}:
            raise ValueError("txn_type must be buy, sell, or dividend")
        return val


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    txn_type: str
    shares: Decimal
    price: Decimal
    fee: Decimal
    traded_at: datetime
    notes: str
    source: str
    created_at: datetime


class TransactionImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
    holdings_updated: int
    realized_pnl: float = 0
    dividends_total: float = 0


class TransactionSummary(BaseModel):
    transaction_count: int
    buy_count: int
    sell_count: int
    realized_pnl: float
    dividends_total: float


class PriceHistoryPoint(BaseModel):
    date: str
    close: float
    volume: float | None = None


class StockHistory(BaseModel):
    ticker: str
    range: str
    currency: str = "USD"
    change_percent: float
    points: list[PriceHistoryPoint]
    source: str = "yahoo"


class DashboardStats(BaseModel):
    holdings_count: int
    total_cost: float
    total_value: float
    total_pnl: float
    total_pnl_percent: float
    usd_rub_rate: float = 0
    total_value_rub: float = 0
    total_cost_rub: float = 0
    top_holdings: list[dict]
    chart_holdings: list[dict] = []


class DividendEvent(BaseModel):
    ticker: str
    ex_date: str
    pay_date: str | None = None
    amount: float
    currency: str = "RUB"
    market: str = "moex"


class HoldingDividendSummary(BaseModel):
    ticker: str
    name: str
    shares: float
    currency: str
    market: str = "us"
    price: float
    dividend_yield: float | None = None
    annual_income: float | None = None
    next_dividend: DividendEvent | None = None
    recent_dividends: list[DividendEvent] = []


class PortfolioDividends(BaseModel):
    usd_rub_rate: float
    total_annual_income_usd: float
    total_annual_income_rub: float
    dividends_received: float
    holdings: list[HoldingDividendSummary]
    upcoming: list[DividendEvent]


class BenchmarkPoint(BaseModel):
    date: str
    portfolio: float
    benchmark: float


class PortfolioBenchmark(BaseModel):
    benchmark: str
    range: str
    portfolio_return: float
    benchmark_return: float
    alpha: float
    max_drawdown_pct: float
    points: list[BenchmarkPoint]


class RiskAlert(BaseModel):
    level: str
    code: str
    title: str
    message: str


class PortfolioRisks(BaseModel):
    score: int
    level: str
    alerts: list[RiskAlert]
    concentration: list[dict]
    sectors: list[dict]
    max_drawdown_pct: float | None = None


class WatchlistCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    notes: str = Field(default="", max_length=500)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class WatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    notes: str
    created_at: datetime
    current_price: float | None = None
    change_percent: float | None = None


class AnalysisRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    current_price: Decimal
    currency: str
    rating: int
    strengths: list[str]
    weaknesses: list[str]
    risks: list[str]
    investment_conclusion: str
    ai_powered: bool
    created_at: datetime


class AlertCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    condition_type: str
    target_value: Decimal = Field(gt=0)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("condition_type")
    @classmethod
    def validate_condition(cls, value: str) -> str:
        allowed = {"above", "below", "change_up", "change_down"}
        if value not in allowed:
            raise ValueError(f"condition_type must be one of {allowed}")
        return value


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    condition_type: str
    target_value: Decimal
    is_active: bool
    last_triggered_at: datetime | None
    created_at: datetime


class PortfolioAnalysis(BaseModel):
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    risks: list[str]
    recommendation: str
    rating: int = Field(ge=1, le=10)
    ai_powered: bool = True
    holdings_count: int
    tickers: list[str]
