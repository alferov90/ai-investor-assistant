"""watchlist, analysis history, price alerts

Revision ID: 003
Revises: 002
Create Date: 2026-06-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
    )
    op.create_index(op.f("ix_watchlist_items_user_id"), "watchlist_items", ["user_id"])

    op.create_table(
        "analysis_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("current_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("investment_conclusion", sa.Text(), nullable=False),
        sa.Column("ai_powered", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analysis_records_user_id"), "analysis_records", ["user_id"])
    op.create_index(op.f("ix_analysis_records_ticker"), "analysis_records", ["ticker"])

    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("condition_type", sa.String(length=20), nullable=False),
        sa.Column("target_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_price_alerts_user_id"), "price_alerts", ["user_id"])
    op.create_index(op.f("ix_price_alerts_is_active"), "price_alerts", ["is_active"])


def downgrade() -> None:
    op.drop_index(op.f("ix_price_alerts_is_active"), table_name="price_alerts")
    op.drop_index(op.f("ix_price_alerts_user_id"), table_name="price_alerts")
    op.drop_table("price_alerts")
    op.drop_index(op.f("ix_analysis_records_ticker"), table_name="analysis_records")
    op.drop_index(op.f("ix_analysis_records_user_id"), table_name="analysis_records")
    op.drop_table("analysis_records")
    op.drop_index(op.f("ix_watchlist_items_user_id"), table_name="watchlist_items")
    op.drop_table("watchlist_items")
