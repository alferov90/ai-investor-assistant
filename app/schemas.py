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


class DashboardStats(BaseModel):
    holdings_count: int
    total_cost: float
    total_value: float
    total_pnl: float
    total_pnl_percent: float
    top_holdings: list[dict]


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
