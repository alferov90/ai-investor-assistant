"""broker connections

Revision ID: 005
Revises: 004
Create Date: 2026-06-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="tinvest"),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("account_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("account_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("access_level", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_mask", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("sandbox", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "account_id", name="uq_broker_user_provider_account"),
    )
    op.create_index("ix_broker_connections_id", "broker_connections", ["id"])
    op.create_index("ix_broker_connections_user_id", "broker_connections", ["user_id"])
    op.create_index("ix_broker_connections_provider", "broker_connections", ["provider"])
    op.create_index("ix_broker_connections_account_id", "broker_connections", ["account_id"])
    op.create_index("ix_broker_connections_is_active", "broker_connections", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_broker_connections_is_active", table_name="broker_connections")
    op.drop_index("ix_broker_connections_account_id", table_name="broker_connections")
    op.drop_index("ix_broker_connections_provider", table_name="broker_connections")
    op.drop_index("ix_broker_connections_user_id", table_name="broker_connections")
    op.drop_index("ix_broker_connections_id", table_name="broker_connections")
    op.drop_table("broker_connections")
