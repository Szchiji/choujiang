"""开奖幂等与事务一致性的真实 PostgreSQL 并发测试。

需要本机临时库，通过 TEST_DATABASE_URL / DATABASE_URL 连接。
不使用 mock 锁来冒充竞态结果。
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url

from app.config import settings
from app.database import normalize_database_url
from app.models import Base, Lottery, Participant, PrizeClaim
import app.database as database
import app.lottery_service as lottery_service


TEST_DB_URL = normalize_database_url(
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or settings.DATABASE_URL
)

PRIZES = [
    {"name": "一等奖", "count": 1},
    {"name": "二等奖", "count": 2},
]
FIXED_BLOCK = {"height": 800000, "hash": "ab" * 32, "source": "test"}


class FakeBot:
    def __init__(self, fail_send: bool = False):
        self.sent = []
        self.fail_send = fail_send
        self.calls = 0

    async def send_message(self, **kwargs):
        self.calls += 1
        if self.fail_send:
            raise RuntimeError("simulated send failure")
        self.sent.append(kwargs)


async def _bind_session(engine, monkeypatch):
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setattr(lottery_service, "async_session", factory)
    return factory


async def _reset_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _create_lottery(factory, *, participants, status="ongoing", **extra):
    async with factory() as db:
        lot = Lottery(
            bot_id=1,
            title=extra.get("title", "并发开奖测试"),
            prizes=PRIZES,
            targets=extra.get("targets", [-100]),
            channels=extra.get("channels"),
            draw_mode=extra.get("draw_mode", "count"),
            draw_time=extra.get("draw_time"),
            target_count=extra.get("target_count", len(participants)),
            status=status,
            is_public=True,
        )
        db.add(lot)
        await db.flush()
        for uid in participants:
            db.add(Participant(
                lottery_id=lot.id,
                user_id=uid,
                username=f"user{uid}",
            ))
        await db.commit()
        await db.refresh(lot)
        return lot.id


async def _load(factory, lottery_id: int):
    async with factory() as db:
        lot = (
            await db.execute(select(Lottery).where(Lottery.id == lottery_id))
        ).scalar_one()
        claims = list(
            (
                await db.execute(
                    select(PrizeClaim).where(PrizeClaim.lottery_id == lottery_id)
                )
            ).scalars().all()
        )
        parts = list(
            (
                await db.execute(
                    select(Participant).where(Participant.lottery_id == lottery_id)
                )
            ).scalars().all()
        )
        return lot, claims, parts


def _winner_ids(winner_list) -> set[int]:
    ids = set()
    if not isinstance(winner_list, dict):
        return ids
    if "reason" in winner_list and len(winner_list) == 1:
        return ids
    for users in winner_list.values():
        if isinstance(users, list):
            ids.update(int(u) for u in users)
    return ids


async def _patch_externals(monkeypatch, *, block=FIXED_BLOCK, enqueue=None):
    async def fake_hash():
        return dict(block)

    async def fake_enqueue(*args, **kwargs):
        if enqueue is not None:
            enqueue.append((args, kwargs))
        return None

    monkeypatch.setattr(lottery_service, "get_latest_block_hash", fake_hash)
    monkeypatch.setattr(lottery_service, "enqueue_retry", fake_enqueue)


async def _with_db(monkeypatch, fn):
    # Destructive schema resets are permitted ONLY in an explicitly named local test DB.
    url = make_url(TEST_DB_URL)
    assert url.host in ("127.0.0.1", "localhost"), "Refusing non-local database"
    assert url.database == "choujiang_draw_test", "Refusing non-test database"
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        poolclass=NullPool,
        connect_args={"timeout": 10},
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
    except Exception as exc:
        await engine.dispose()
        pytest.fail(
            f"无法连接测试 PostgreSQL（{TEST_DB_URL}）：{exc}。"
            "并发测试需要真实数据库，不能在无库环境下用 mock 替代。"
        )
    factory = await _bind_session(engine, monkeypatch)
    await _reset_schema(engine)
    retries = []
    await _patch_externals(monkeypatch, enqueue=retries)
    try:
        return await fn(factory, retries)
    finally:
        await engine.dispose()


def _run(monkeypatch, fn):
    return asyncio.run(_with_db(monkeypatch, fn))


def test_concurrent_draw_produces_single_result(monkeypatch):
    async def body(factory, _retries):
        user_ids = list(range(1001, 1011))
        lottery_id = await _create_lottery(factory, participants=user_ids)
        bot = FakeBot()

        async def one():
            async with factory() as db:
                lot = (
                    await db.execute(select(Lottery).where(Lottery.id == lottery_id))
                ).scalar_one()
            await lottery_service.execute_draw(bot, lot)

        await asyncio.gather(*[one() for _ in range(8)])

        lot, claims, parts = await _load(factory, lottery_id)
        assert lot.status == "ended"
        winners = _winner_ids(lot.winner_list)
        assert winners, f"应有中奖名单，实际为 {lot.winner_list}"
        assert len(winners) == 3
        assert len(claims) == 3
        assert {c.user_id for c in claims} == winners
        assert {(c.prize_name, c.user_id) for c in claims} == {
            (prize, uid)
            for prize, uids in lot.winner_list.items()
            for uid in uids
        }
        assert len({c.claim_code for c in claims}) == 3
        assert len(parts) == 10
        assert bot.calls == 4  # one announcement + three winner notifications

    _run(monkeypatch, body)


def test_mid_transaction_failure_rolls_back_and_is_retryable(monkeypatch):
    async def body(factory, _retries):
        user_ids = list(range(2001, 2011))
        lottery_id = await _create_lottery(factory, participants=user_ids)

        async def boom():
            raise RuntimeError("simulated flush failure")

        monkeypatch.setattr(lottery_service, "_after_draw_rows_flushed", boom)

        async with factory() as db:
            lot = (
                await db.execute(select(Lottery).where(Lottery.id == lottery_id))
            ).scalar_one()
        await lottery_service.execute_draw(FakeBot(), lot)

        lot, claims, _ = await _load(factory, lottery_id)
        assert lot.status == "drawing"
        assert lot.winner_list is None
        assert claims == []

        async def ok_flush():
            return None

        monkeypatch.setattr(lottery_service, "_after_draw_rows_flushed", ok_flush)
        await lottery_service.execute_draw(FakeBot(), lot)

        lot, claims, _ = await _load(factory, lottery_id)
        assert lot.status == "ended"
        winners = _winner_ids(lot.winner_list)
        assert len(winners) == 3
        assert {c.user_id for c in claims} == winners

    _run(monkeypatch, body)


def test_second_draw_does_not_change_committed_result(monkeypatch):
    async def body(factory, _retries):
        user_ids = list(range(3001, 3011))
        lottery_id = await _create_lottery(factory, participants=user_ids)
        async with factory() as db:
            lot = (
                await db.execute(select(Lottery).where(Lottery.id == lottery_id))
            ).scalar_one()
        await lottery_service.execute_draw(FakeBot(), lot)
        lot1, claims1, _ = await _load(factory, lottery_id)
        snapshot = {
            "status": lot1.status,
            "winners": lot1.winner_list,
            "hash": lot1.block_hash,
            "height": lot1.block_height,
            "codes": sorted((c.user_id, c.prize_name, c.claim_code) for c in claims1),
        }
        assert snapshot["status"] == "ended"

        async def other_hash():
            return {"height": 1, "hash": "ff" * 32, "source": "other"}

        monkeypatch.setattr(lottery_service, "get_latest_block_hash", other_hash)
        await lottery_service.execute_draw(FakeBot(), lot)
        result = await lottery_service.manual_draw(FakeBot(), lottery_id)
        assert result["ok"] is False

        lot2, claims2, _ = await _load(factory, lottery_id)
        assert lot2.status == snapshot["status"]
        assert lot2.winner_list == snapshot["winners"]
        assert lot2.block_hash == snapshot["hash"]
        assert lot2.block_height == snapshot["height"]
        assert sorted((c.user_id, c.prize_name, c.claim_code) for c in claims2) == snapshot["codes"]
        assert len(claims2) == 3

    _run(monkeypatch, body)


def test_send_failure_does_not_change_committed_result(monkeypatch):
    async def body(factory, retries):
        user_ids = list(range(4001, 4011))
        lottery_id = await _create_lottery(
            factory, participants=user_ids, targets=[-200, -201]
        )
        bot = FakeBot(fail_send=True)
        async with factory() as db:
            lot = (
                await db.execute(select(Lottery).where(Lottery.id == lottery_id))
            ).scalar_one()
        await lottery_service.execute_draw(bot, lot)

        lot, claims, _ = await _load(factory, lottery_id)
        assert lot.status == "ended"
        winners = _winner_ids(lot.winner_list)
        assert len(winners) == 3
        assert {c.user_id for c in claims} == winners
        assert bot.calls > 0
        assert retries, "公告发送失败应进入重试队列，而不是回滚开奖结果"

    _run(monkeypatch, body)


def test_concurrent_same_user_join_is_unique(monkeypatch):
    async def body(factory, _retries):
        lottery_id = await _create_lottery(factory, participants=[], target_count=5)

        results = await asyncio.gather(*[
            lottery_service.try_add_participant(lottery_id, 9001, "dup")
            for _ in range(8)
        ])
        statuses = [r[0] for r in results]
        assert statuses.count("ok") == 1
        assert statuses.count("already") == 7
        _lot, _claims, parts = await _load(factory, lottery_id)
        assert len(parts) == 1
        assert parts[0].user_id == 9001

    _run(monkeypatch, body)


def test_join_rejected_during_draw_and_after_end(monkeypatch):
    async def body(factory, _retries):
        user_ids = list(range(5001, 5011))
        lottery_id = await _create_lottery(factory, participants=user_ids)
        claimed = asyncio.Event()
        proceed = asyncio.Event()

        async def slow_hash():
            claimed.set()
            await proceed.wait()
            return dict(FIXED_BLOCK)

        monkeypatch.setattr(lottery_service, "get_latest_block_hash", slow_hash)

        async with factory() as db:
            lot = (
                await db.execute(select(Lottery).where(Lottery.id == lottery_id))
            ).scalar_one()

        draw_task = asyncio.create_task(lottery_service.execute_draw(FakeBot(), lot))
        await asyncio.wait_for(claimed.wait(), timeout=5)

        mid_status, _ = await lottery_service.try_add_participant(
            lottery_id, 5999, "late"
        )
        assert mid_status == "ended"

        async with factory() as db:
            mid = (
                await db.execute(select(Lottery).where(Lottery.id == lottery_id))
            ).scalar_one()
            assert mid.status == "drawing"

        proceed.set()
        await draw_task

        after_status, _ = await lottery_service.try_add_participant(
            lottery_id, 5998, "later"
        )
        assert after_status == "ended"

        lot, claims, parts = await _load(factory, lottery_id)
        assert lot.status == "ended"
        assert {p.user_id for p in parts} == set(user_ids)
        assert 5999 not in {p.user_id for p in parts}
        assert 5998 not in {p.user_id for p in parts}
        assert _winner_ids(lot.winner_list) == {c.user_id for c in claims}

    _run(monkeypatch, body)


def test_get_due_lotteries_includes_stuck_drawing(monkeypatch):
    async def body(factory, _retries):
        past = datetime.now() - timedelta(minutes=5)
        future = datetime.now() + timedelta(hours=1)
        due_id = await _create_lottery(
            factory,
            participants=list(range(6001, 6006)),
            draw_mode="time",
            draw_time=past,
            status="ongoing",
        )
        stuck_id = await _create_lottery(
            factory,
            participants=list(range(6101, 6106)),
            draw_mode="count",
            status="drawing",
        )
        future_id = await _create_lottery(
            factory,
            participants=list(range(6201, 6206)),
            draw_mode="time",
            draw_time=future,
            status="ongoing",
        )
        due = await lottery_service.get_due_lotteries()
        ids = {lot.id for lot in due}
        assert due_id in ids
        assert stuck_id in ids
        assert future_id not in ids

    _run(monkeypatch, body)


def test_mark_ended_does_not_overwrite_winners(monkeypatch):
    async def body(factory, _retries):
        lottery_id = await _create_lottery(
            factory, participants=list(range(7001, 7011))
        )
        async with factory() as db:
            lot = (
                await db.execute(select(Lottery).where(Lottery.id == lottery_id))
            ).scalar_one()
        await lottery_service.execute_draw(FakeBot(), lot)
        lot1, claims1, _ = await _load(factory, lottery_id)
        assert lot1.status == "ended"

        updated = await lottery_service.mark_ended(
            lottery_id, "开奖异常: should not overwrite"
        )
        assert updated is False
        lot2, claims2, _ = await _load(factory, lottery_id)
        assert lot2.winner_list == lot1.winner_list
        assert "reason" not in (lot2.winner_list or {})
        assert sorted(c.claim_code for c in claims2) == sorted(
            c.claim_code for c in claims1
        )

    _run(monkeypatch, body)


def test_cancelled_draw_rolls_back_and_recovers(monkeypatch):
    async def body(factory, _retries):
        lottery_id = await _create_lottery(
            factory, participants=list(range(8001, 8011))
        )
        entered = asyncio.Event()
        never = asyncio.Event()

        async def pause_after_flush():
            entered.set()
            await never.wait()

        monkeypatch.setattr(
            lottery_service, "_after_draw_rows_flushed", pause_after_flush
        )
        lot, _, _ = await _load(factory, lottery_id)
        task = asyncio.create_task(lottery_service.execute_draw(FakeBot(), lot))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        lot, claims, _ = await _load(factory, lottery_id)
        assert lot.status == "drawing"
        assert lot.winner_list is None
        assert claims == []

        async def resume():
            return None

        monkeypatch.setattr(lottery_service, "_after_draw_rows_flushed", resume)
        result = await lottery_service.manual_draw(FakeBot(), lottery_id)
        assert result["ok"]
        lot, claims, _ = await _load(factory, lottery_id)
        assert lot.status == "ended"
        assert _winner_ids(lot.winner_list) == {c.user_id for c in claims}
        assert len(claims) == 3

    _run(monkeypatch, body)
