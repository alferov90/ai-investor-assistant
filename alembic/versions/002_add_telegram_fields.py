"""add telegram fields to users

Revision ID: 002
Revises: 001
Create Date: 2026-06-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("telegram_link_token", sa.String(length=64), nullable=True))
    op.create_index(
        op.f("ix_users_telegram_link_token"), "users", ["telegram_link_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_telegram_link_token"), table_name="users")
    op.drop_column("users", "telegram_link_token")
    op.drop_column("users", "telegram_chat_id")
