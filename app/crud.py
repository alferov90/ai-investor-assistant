import secrets

from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.security import hash_password


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_telegram_chat_id(db: Session, chat_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.telegram_chat_id == chat_id).first()


def get_user_by_link_token(db: Session, token: str) -> models.User | None:
    return db.query(models.User).filter(models.User.telegram_link_token == token).first()


def create_telegram_link(db: Session, user: models.User) -> str:
    if not user.telegram_link_token:
        user.telegram_link_token = secrets.token_hex(24)
        db.commit()
        db.refresh(user)
    username = settings.telegram_bot_username.lstrip("@")
    return f"https://t.me/{username}?start={user.telegram_link_token}"


def link_telegram(db: Session, user: models.User, chat_id: int) -> None:
    user.telegram_chat_id = chat_id
    user.telegram_link_token = None
    db.commit()


def unlink_telegram(db: Session, user: models.User) -> None:
    user.telegram_chat_id = None
    user.telegram_link_token = None
    db.commit()


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


# --- Watchlist ---


def list_watchlist(db: Session, user_id: int) -> list[models.WatchlistItem]:
    return (
        db.query(models.WatchlistItem)
        .filter(models.WatchlistItem.user_id == user_id)
        .order_by(models.WatchlistItem.ticker)
        .all()
    )


def get_watchlist_item(db: Session, user_id: int, item_id: int) -> models.WatchlistItem | None:
    return (
        db.query(models.WatchlistItem)
        .filter(models.WatchlistItem.id == item_id, models.WatchlistItem.user_id == user_id)
        .first()
    )


def create_watchlist_item(
    db: Session, user_id: int, data: schemas.WatchlistCreate
) -> models.WatchlistItem:
    item = models.WatchlistItem(user_id=user_id, ticker=data.ticker, notes=data.notes)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_watchlist_item(db: Session, item: models.WatchlistItem) -> None:
    db.delete(item)
    db.commit()


def get_watchlist_by_ticker(
    db: Session, user_id: int, ticker: str
) -> models.WatchlistItem | None:
    return (
        db.query(models.WatchlistItem)
        .filter(
            models.WatchlistItem.user_id == user_id,
            models.WatchlistItem.ticker == ticker.upper(),
        )
        .first()
    )


def delete_watchlist_by_ticker(db: Session, user_id: int, ticker: str) -> bool:
    item = get_watchlist_by_ticker(db, user_id, ticker)
    if not item:
        return False
    delete_watchlist_item(db, item)
    return True


def list_telegram_users(db: Session) -> list[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.telegram_chat_id.isnot(None))
        .all()
    )


# --- Analysis history ---


def save_analysis(db: Session, user_id: int, analysis: schemas.StockAnalysis) -> models.AnalysisRecord:
    record = models.AnalysisRecord(
        user_id=user_id,
        ticker=analysis.ticker,
        name=analysis.name,
        current_price=analysis.current_price,
        currency=analysis.currency,
        rating=analysis.rating,
        strengths=analysis.strengths,
        weaknesses=analysis.weaknesses,
        risks=analysis.risks,
        investment_conclusion=analysis.investment_conclusion,
        ai_powered=analysis.ai_powered,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_analyses(
    db: Session, user_id: int, ticker: str | None = None, limit: int = 50
) -> list[models.AnalysisRecord]:
    q = db.query(models.AnalysisRecord).filter(models.AnalysisRecord.user_id == user_id)
    if ticker:
        q = q.filter(models.AnalysisRecord.ticker == ticker.upper())
    return q.order_by(models.AnalysisRecord.created_at.desc()).limit(limit).all()


def get_analysis_record(
    db: Session, user_id: int, record_id: int
) -> models.AnalysisRecord | None:
    return (
        db.query(models.AnalysisRecord)
        .filter(models.AnalysisRecord.id == record_id, models.AnalysisRecord.user_id == user_id)
        .first()
    )


# --- Price alerts ---


def list_alerts(db: Session, user_id: int) -> list[models.PriceAlert]:
    return (
        db.query(models.PriceAlert)
        .filter(models.PriceAlert.user_id == user_id)
        .order_by(models.PriceAlert.created_at.desc())
        .all()
    )


def list_active_alerts(db: Session) -> list[models.PriceAlert]:
    return (
        db.query(models.PriceAlert)
        .filter(models.PriceAlert.is_active.is_(True))
        .all()
    )


def create_alert(db: Session, user_id: int, data: schemas.AlertCreate) -> models.PriceAlert:
    alert = models.PriceAlert(
        user_id=user_id,
        ticker=data.ticker,
        condition_type=data.condition_type,
        target_value=data.target_value,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_alert(db: Session, user_id: int, alert_id: int) -> models.PriceAlert | None:
    return (
        db.query(models.PriceAlert)
        .filter(models.PriceAlert.id == alert_id, models.PriceAlert.user_id == user_id)
        .first()
    )


def delete_alert(db: Session, alert: models.PriceAlert) -> None:
    db.delete(alert)
    db.commit()


def toggle_alert(db: Session, alert: models.PriceAlert, active: bool) -> models.PriceAlert:
    alert.is_active = active
    db.commit()
    db.refresh(alert)
    return alert


def mark_alert_triggered(db: Session, alert: models.PriceAlert) -> None:
    from datetime import datetime, timezone

    alert.last_triggered_at = datetime.now(timezone.utc)
    db.commit()


# --- Transactions ---


def list_transactions(
    db: Session, user_id: int, ticker: str | None = None, limit: int = 200
) -> list[models.PortfolioTransaction]:
    q = db.query(models.PortfolioTransaction).filter(
        models.PortfolioTransaction.user_id == user_id
    )
    if ticker:
        q = q.filter(models.PortfolioTransaction.ticker == ticker.upper())
    return q.order_by(models.PortfolioTransaction.traded_at.desc()).limit(limit).all()


def get_transaction(
    db: Session, user_id: int, txn_id: int
) -> models.PortfolioTransaction | None:
    return (
        db.query(models.PortfolioTransaction)
        .filter(
            models.PortfolioTransaction.id == txn_id,
            models.PortfolioTransaction.user_id == user_id,
        )
        .first()
    )


def create_transaction(
    db: Session, user_id: int, data: schemas.TransactionCreate, source: str = "manual"
) -> models.PortfolioTransaction:
    txn = models.PortfolioTransaction(
        user_id=user_id,
        ticker=data.ticker,
        txn_type=data.txn_type,
        shares=data.shares,
        price=data.price,
        fee=data.fee,
        traded_at=data.traded_at,
        notes=data.notes,
        source=source,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def create_transactions_bulk(
    db: Session, user_id: int, rows: list[schemas.TransactionCreate], source: str = "csv"
) -> list[models.PortfolioTransaction]:
    created: list[models.PortfolioTransaction] = []
    for data in rows:
        txn = models.PortfolioTransaction(
            user_id=user_id,
            ticker=data.ticker,
            txn_type=data.txn_type,
            shares=data.shares,
            price=data.price,
            fee=data.fee,
            traded_at=data.traded_at,
            notes=data.notes,
            source=source,
        )
        db.add(txn)
        created.append(txn)
    db.commit()
    for txn in created:
        db.refresh(txn)
    return created


def delete_transaction(db: Session, txn: models.PortfolioTransaction) -> None:
    db.delete(txn)
    db.commit()


def get_latest_analysis_rating(db: Session, user_id: int, ticker: str) -> int | None:
    record = (
        db.query(models.AnalysisRecord)
        .filter(
            models.AnalysisRecord.user_id == user_id,
            models.AnalysisRecord.ticker == ticker.upper(),
        )
        .order_by(models.AnalysisRecord.created_at.desc())
        .first()
    )
    return record.rating if record else None
