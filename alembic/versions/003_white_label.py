"""add white-label columns to bots

Revision ID: 003_white
Revises: 002_unique
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_white"
down_revision: Union[str, None] = "002_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("custom_name", sa.String(100), nullable=True))
    op.add_column("bots", sa.Column("custom_welcome", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bots", "custom_welcome")
    op.drop_column("bots", "custom_name")
