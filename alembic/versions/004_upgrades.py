"""revenue, templates, prize claims

Revision ID: 004_upgrades
Revises: 003_white
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_upgrades"
down_revision: Union[str, None] = "003_white"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clone_applications", sa.Column("amount_stars", sa.Integer(), server_default="0"))

    op.create_table(
        "lottery_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(100)),
        sa.Column("config", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "prize_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lottery_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("prize_name", sa.String(200)),
        sa.Column("claim_code", sa.String(32), unique=True),
        sa.Column("claimed", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("prize_claims")
    op.drop_table("lottery_templates")
    op.drop_column("clone_applications", "amount_stars")
