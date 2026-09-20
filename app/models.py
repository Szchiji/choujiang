from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, Text, JSON,
)
from sqlalchemy.sql import func
from app.database import Base


class Bot(Base):
    __tablename__ = "bots"
    id = Column(Integer, primary_key=True)
    owner_id = Column(BigInteger, nullable=False)
    bot_token = Column(String(255), unique=True)
    bot_username = Column(String(100))
    is_master = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    expire_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Lottery(Base):
    __tablename__ = "lotteries"
    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer, nullable=False)
    title = Column(String(200))
    subtitle = Column(String(200), nullable=True)
    cover_image = Column(Text, nullable=True)
    prizes = Column(JSON)
    targets = Column(JSON)
    channels = Column(JSON)
    draw_mode = Column(String(20), default="time")
    draw_time = Column(DateTime, nullable=True)
    target_count = Column(Integer, nullable=True)
    block_hash = Column(String(100), nullable=True)
    block_height = Column(Integer, nullable=True)
    status = Column(String(20), default="draft")
    is_public = Column(Boolean, default=True)
    winner_list = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Participant(Base):
    __tablename__ = "participants"
    id = Column(Integer, primary_key=True)
    lottery_id = Column(Integer, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(100), nullable=True)
    join_time = Column(DateTime, server_default=func.now())


class UserMeta(Base):
    __tablename__ = "user_meta"
    user_id = Column(BigInteger, primary_key=True)
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    free_quota = Column(Integer, default=1)
    extra_credits = Column(Integer, default=0)
    sign_in_streak = Column(Integer, default=0)
    last_sign_in = Column(DateTime, nullable=True)
    referral_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class CloneApplication(Base):
    __tablename__ = "clone_applications"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    bot_name = Column(String(100))
    bot_token = Column(String(255))
    plan = Column(String(20))
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, server_default=func.now())
    processed_at = Column(DateTime, nullable=True)


class Referral(Base):
    __tablename__ = "referrals"
    id = Column(Integer, primary_key=True)
    inviter_id = Column(BigInteger, nullable=False)
    invitee_id = Column(BigInteger, nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now())
