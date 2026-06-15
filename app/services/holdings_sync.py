"""Sync portfolio holdings from transaction journal."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app import crud, models


@dataclass
class _Position:
    shares: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")

    @property
    def avg_price(self) -> Decimal:
        if self.shares <= 0:
            return Decimal("0")
        return self.cost_basis / self.shares


@dataclass
class RebuildResult:
    holdings_count: int = 0
    realized_pnl: float = 0.0
    dividends_total: float = 0.0


def _apply_txn(
    positions: dict[str, _Position],
    realized: Decimal,
    dividends: Decimal,
    txn: models.PortfolioTransaction,
) -> tuple[Decimal, Decimal]:
    ticker = txn.ticker.upper()
    pos = positions.setdefault(ticker, _Position())
    shares = Decimal(txn.shares)
    price = Decimal(txn.price)
    fee = Decimal(txn.fee or 0)
    txn_type = txn.txn_type.lower()

    if txn_type == "buy":
        pos.shares += shares
        pos.cost_basis += shares * price + fee
    elif txn_type == "sell":
        if shares > pos.shares:
            shares = pos.shares
        if shares > 0:
            avg = pos.avg_price
            realized += shares * price - fee - shares * avg
            pos.cost_basis -= shares * avg
            pos.shares -= shares
            if pos.shares <= 0:
                pos.shares = Decimal("0")
                pos.cost_basis = Decimal("0")
    elif txn_type == "dividend":
        dividends += price
    return realized, dividends


def rebuild_holdings_from_transactions(db: Session, user_id: int) -> RebuildResult:
    txns = crud.list_transactions(db, user_id, limit=10_000)
    positions: dict[str, _Position] = {}
    realized = Decimal("0")
    dividends = Decimal("0")

    for txn in sorted(txns, key=lambda t: t.traded_at):
        realized, dividends = _apply_txn(positions, realized, dividends, txn)

    existing = {h.ticker: h for h in crud.list_holdings(db, user_id)}
    seen: set[str] = set()

    for ticker, pos in positions.items():
        if pos.shares <= 0:
            continue
        seen.add(ticker)
        avg = round(float(pos.avg_price), 4)
        if ticker in existing:
            existing[ticker].shares = pos.shares
            existing[ticker].avg_price = Decimal(str(avg))
        else:
            db.add(
                models.PortfolioHolding(
                    user_id=user_id,
                    ticker=ticker,
                    shares=pos.shares,
                    avg_price=Decimal(str(avg)),
                    notes="Из журнала сделок",
                )
            )

    for ticker, holding in existing.items():
        if ticker not in seen:
            db.delete(holding)

    db.commit()

    return RebuildResult(
        holdings_count=len(seen),
        realized_pnl=float(realized),
        dividends_total=float(dividends),
    )


def compute_transaction_summary(db: Session, user_id: int) -> dict:
    txns = crud.list_transactions(db, user_id, limit=10_000)
    positions: dict[str, _Position] = {}
    realized = Decimal("0")
    dividends = Decimal("0")
    buys = sells = 0

    for txn in sorted(txns, key=lambda t: t.traded_at):
        txn_type = txn.txn_type.lower()
        if txn_type == "buy":
            buys += 1
        elif txn_type == "sell":
            sells += 1
        realized, dividends = _apply_txn(positions, realized, dividends, txn)

    return {
        "transaction_count": len(txns),
        "buy_count": buys,
        "sell_count": sells,
        "realized_pnl": round(float(realized), 2),
        "dividends_total": round(float(dividends), 2),
    }
