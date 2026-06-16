"""broker orders

Revision ID: 006
Revises: 005
Create Date: 2026-06-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="tinvest"),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False, server_default="limit"),
        sa.Column("lots_requested", sa.Integer(), nullable=False),
        sa.Column("lots_executed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("limit_price", sa.Numeric(18, 9), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("message", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("sandbox", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["broker_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broker_orders_id", "broker_orders", ["id"])
    op.create_index("ix_broker_orders_user_id", "broker_orders", ["user_id"])
    op.create_index("ix_broker_orders_connection_id", "broker_orders", ["connection_id"])
    op.create_index("ix_broker_orders_account_id", "broker_orders", ["account_id"])
    op.create_index("ix_broker_orders_order_id", "broker_orders", ["order_id"])
    op.create_index("ix_broker_orders_request_id", "broker_orders", ["request_id"])
    op.create_index("ix_broker_orders_ticker", "broker_orders", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_broker_orders_ticker", table_name="broker_orders")
    op.drop_index("ix_broker_orders_request_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_order_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_account_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_connection_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_user_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_id", table_name="broker_orders")
    op.drop_table("broker_orders")
