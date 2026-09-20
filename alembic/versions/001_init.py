"""init tables

Revision ID: 001_init
Revises:
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== bots ==========
    op.create_table(
        "bots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_token", sa.String(255), unique=True),
        sa.Column("bot_username", sa.String(100)),
        sa.Column("is_master", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("expire_time", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ========== lotteries ==========
    op.create_table(
        "lotteries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("subtitle", sa.String(200), nullable=True),
        sa.Column("cover_image", sa.Text(), nullable=True),
        sa.Column("prizes", sa.JSON()),
        sa.Column("targets", sa.JSON()),
        sa.Column("channels", sa.JSON()),
        sa.Column("draw_mode", sa.String(20), server_default="time"),
        sa.Column("draw_time", sa.DateTime(), nullable=True),
        sa.Column("target_count", sa.Integer(), nullable=True),
        sa.Column("block_hash", sa.String(100), nullable=True),
        sa.Column("block_height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("winner_list", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ========== participants ==========
    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lottery_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("join_time", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_participants_lottery", "participants", ["lottery_id"])
    op.create_index("ix_participants_user", "participants", ["user_id"])

    # ========== user_meta ==========
    op.create_table(
        "user_meta",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("trial_start", sa.DateTime(), nullable=True),
        sa.Column("trial_end", sa.DateTime(), nullable=True),
        sa.Column("free_quota", sa.Integer(), server_default="1"),
        sa.Column("extra_credits", sa.Integer(), server_default="0"),
        sa.Column("sign_in_streak", sa.Integer(), server_default="0"),
        sa.Column("last_sign_in", sa.DateTime(), nullable=True),
        sa.Column("referral_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ========== clone_applications ==========
    op.create_table(
        "clone_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_name", sa.String(100)),
        sa.Column("bot_token", sa.String(255)),
        sa.Column("plan", sa.String(20)),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )

    # ========== referrals ==========
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inviter_id", sa.BigInteger(), nullable=False),
        sa.Column("invitee_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_table("clone_applications")
    op.drop_table("user_meta")
    op.drop_index("ix_participants_user", table_name="participants")
    op.drop_index("ix_participants_lottery", table_name="participants")
    op.drop_table("participants")
    op.drop_table("lotteries")
    op.drop_table("bots")
