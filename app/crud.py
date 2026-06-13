from sqlalchemy.orm import Session

from app import models, schemas
from app.security import hash_password


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    db_user = models.User(
        email=user.email.lower(),
        name=user.name.strip(),
        hashed_password=hash_password(user.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def list_holdings(db: Session, user_id: int) -> list[models.PortfolioHolding]:
    return (
        db.query(models.PortfolioHolding)
        .filter(models.PortfolioHolding.user_id == user_id)
        .order_by(models.PortfolioHolding.ticker)
        .all()
    )


def get_holding(db: Session, user_id: int, holding_id: int) -> models.PortfolioHolding | None:
    return (
        db.query(models.PortfolioHolding)
        .filter(
            models.PortfolioHolding.id == holding_id,
            models.PortfolioHolding.user_id == user_id,
        )
        .first()
    )


def get_holding_by_ticker(
    db: Session, user_id: int, ticker: str
) -> models.PortfolioHolding | None:
    return (
        db.query(models.PortfolioHolding)
        .filter(
            models.PortfolioHolding.user_id == user_id,
            models.PortfolioHolding.ticker == ticker.upper(),
        )
        .first()
    )


def create_holding(
    db: Session, user_id: int, data: schemas.PortfolioHoldingCreate
) -> models.PortfolioHolding:
    holding = models.PortfolioHolding(
        user_id=user_id,
        ticker=data.ticker,
        shares=data.shares,
        avg_price=data.avg_price,
        notes=data.notes,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return holding


def update_holding(
    db: Session, holding: models.PortfolioHolding, data: schemas.PortfolioHoldingUpdate
) -> models.PortfolioHolding:
    if data.shares is not None:
        holding.shares = data.shares
    if data.avg_price is not None:
        holding.avg_price = data.avg_price
    if data.notes is not None:
        holding.notes = data.notes
    db.commit()
    db.refresh(holding)
    return holding


def delete_holding(db: Session, holding: models.PortfolioHolding) -> None:
    db.delete(holding)
    db.commit()


def portfolio_totals(
    holdings: list[models.PortfolioHolding], prices: dict[str, float]
) -> tuple[float, float]:
    total_cost = 0.0
    total_value = 0.0
    for holding in holdings:
        shares = float(holding.shares)
        avg_price = float(holding.avg_price)
        price = prices.get(holding.ticker, avg_price)
        total_cost += shares * avg_price
        total_value += shares * price
    return total_cost, total_value
