"""add unique constraint on prize_claims (lottery_id, user_id)

Revision ID: 005_draw
Revises: 004_upgrades
Create Date: 2026-11-16

报名唯一约束已在 002_unique 中定义；本迁移仅补齐核销记录防重。
开奖中间态 drawing 复用现有 lotteries.status 字符串列，无需改表结构。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005_draw"
down_revision: Union[str, None] = "004_upgrades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_prize_claims_lottery_user",
        "prize_claims",
        ["lottery_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_prize_claims_lottery_user",
        "prize_claims",
        type_="unique",
    )
