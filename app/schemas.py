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


class StockAnalysis(BaseModel):
    ticker: str
    quote: StockQuote
    summary: str
    strengths: list[str]
    risks: list[str]
    recommendation: str
    ai_powered: bool


class DashboardStats(BaseModel):
    holdings_count: int
    total_cost: float
    total_value: float
    total_pnl: float
    total_pnl_percent: float
    top_holdings: list[dict]
