"""add unique constraint on participants (lottery_id, user_id)

Revision ID: 002_unique
Revises: 001_init
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_unique"
down_revision: Union[str, None] = "001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_participants_lottery_user",
        "participants",
        ["lottery_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_participants_lottery_user",
        "participants",
        type_="unique",
    )
