from datetime import datetime
import secrets

from sqlalchemy import select, update, or_, and_, func
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models import Lottery, Participant, PrizeClaim
from app.blockchain import get_latest_block_hash, draw_winners
from app.channel_checker import check_channels_for_draw
from app.config import settings
from app.retry_queue import enqueue_retry


STATUS_ONGOING = "ongoing"
STATUS_DRAWING = "drawing"
STATUS_ENDED = "ended"


async def get_due_lotteries() -> list:
    """到期的定时开奖，以及卡在 drawing 的未完成开奖（可重试）。"""
    async with async_session() as db:
        now = datetime.now()
        stmt = select(Lottery).where(
            or_(
                and_(
                    Lottery.status == STATUS_ONGOING,
                    Lottery.draw_mode == "time",
                    Lottery.draw_time <= now,
                ),
                Lottery.status == STATUS_DRAWING,
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_participants(lottery_id: int) -> list:
    async with async_session() as db:
        stmt = select(Participant.user_id).where(
            Participant.lottery_id == lottery_id
        )
        result = await db.execute(stmt)
        return [row[0] for row in result.all()]


async def get_participant_count(lottery_id: int) -> int:
    async with async_session() as db:
        stmt = select(func.count(Participant.id)).where(
            Participant.lottery_id == lottery_id
        )
        result = await db.execute(stmt)
        return int(result.scalar() or 0)


async def try_add_participant(
    lottery_id: int, user_id: int, username: str | None = None
) -> tuple[str, int]:
    """在同一事务中锁定活动行再写入报名，拒绝已冻结/已结束活动。

    返回 (status, count)，status 为 ok / already / ended / not_found。
    """
    try:
        async with async_session() as db:
            async with db.begin():
                lottery = (
                    await db.execute(
                        select(Lottery)
                        .where(Lottery.id == lottery_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if not lottery:
                    return "not_found", 0
                if lottery.status != STATUS_ONGOING:
                    return "ended", 0
                db.add(Participant(
                    lottery_id=lottery_id,
                    user_id=user_id,
                    username=username,
                ))
                await db.flush()
                count = (
                    await db.execute(
                        select(func.count(Participant.id)).where(
                            Participant.lottery_id == lottery_id
                        )
                    )
                ).scalar() or 0
                return "ok", int(count)
    except IntegrityError as exc:
        cause = getattr(exc.orig, "__cause__", None)
        if getattr(cause, "constraint_name", None) != "uq_participants_lottery_user":
            raise
        return "already", 0


async def _claim_draw(lottery_id: int):
    """用行锁把 ongoing 原子切换为 drawing；已在 drawing 且无结果则允许恢复。

    返回应对该活动执行开奖计算的 Lottery 快照；已有终态则返回 None。
    """
    async with async_session() as db:
        async with db.begin():
            lottery = (
                await db.execute(
                    select(Lottery)
                    .where(Lottery.id == lottery_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if not lottery:
                return None

            if lottery.status == STATUS_ENDED:
                return None

            if lottery.winner_list is not None:
                if lottery.status != STATUS_ENDED:
                    lottery.status = STATUS_ENDED
                return None

            if lottery.status == STATUS_DRAWING:
                return lottery

            if lottery.status != STATUS_ONGOING:
                return None

            lottery.status = STATUS_DRAWING
            await db.flush()
            return lottery


async def _after_draw_rows_flushed():
    """测试缝：测试可将其替换为抛错，以验证事务回滚与可重试。"""
    return


async def _commit_draw_result(lottery_id: int, winners: dict, block_info: dict):
    """在同一事务中写入 winner_list、核销记录并置为 ended。

    若活动已不再是无结果的 drawing（已被其他进程提交或取消），则回滚并返回 None。
    """
    async with async_session() as db:
        async with db.begin():
            lottery = (
                await db.execute(
                    select(Lottery)
                    .where(Lottery.id == lottery_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if not lottery:
                return None
            if (
                lottery.status != STATUS_DRAWING
                or lottery.winner_list is not None
            ):
                return None

            claim_codes = {}
            for prize_name, user_ids in winners.items():
                for uid in user_ids:
                    code = secrets.token_hex(6).upper()
                    db.add(PrizeClaim(
                        lottery_id=lottery_id,
                        user_id=uid,
                        prize_name=prize_name,
                        claim_code=code,
                    ))
                    claim_codes[(prize_name, uid)] = code

            lottery.winner_list = winners
            lottery.block_hash = block_info["hash"]
            lottery.block_height = block_info.get("height", 0)
            lottery.status = STATUS_ENDED
            await db.flush()
            await _after_draw_rows_flushed()
            return claim_codes


async def execute_draw(bot, lottery):
    lottery_id = lottery.id
    finalized = False
    try:
        claimed = await _claim_draw(lottery_id)
        if not claimed:
            print(f"⏭️ 活动 {lottery_id} 已有终态或不可开奖，跳过")
            return

        lottery = claimed
        print(f"🎯 开始开奖：{lottery.title} (ID: {lottery_id})")

        participants = await get_participants(lottery_id)
        if not participants:
            await mark_ended(lottery_id, "参与人数为 0，自动取消")
            return

        channels = lottery.channels or []
        if channels:
            valid = []
            for uid in participants:
                try:
                    if await check_channels_for_draw(bot, uid, channels):
                        valid.append(uid)
                except Exception as e:
                    print(f"校验用户 {uid} 频道失败: {e}")

            print(f"⚠️ 开奖前过滤：{len(participants)} → {len(valid)} 人")
            participants = valid

        if not participants:
            await mark_ended(lottery_id, "所有参与者已取关，取消开奖")
            return

        prizes = lottery.prizes or []
        total_prizes = sum(p.get("count", 0) for p in prizes)
        if len(participants) < total_prizes:
            await mark_ended(
                lottery_id,
                f"有效参与人数({len(participants)})少于奖品总数({total_prizes})",
            )
            return

        try:
            block_info = await get_latest_block_hash()
        except Exception as e:
            print(f"❌ 获取区块链哈希失败: {e}")
            import hashlib
            import time
            fake_seed = hashlib.sha256(f"{lottery_id}_{time.time()}".encode()).hexdigest()
            block_info = {
                "height": 0,
                "hash": fake_seed,
                "fallback": True,
            }

        winners = draw_winners(
            participants=participants,
            prizes=prizes,
            block_hash=block_info["hash"],
            lottery_id=lottery_id,
        )
        if not winners:
            await mark_ended(lottery_id, "抽奖算法返回空结果")
            return

        claim_codes = await _commit_draw_result(lottery_id, winners, block_info)
        if not claim_codes:
            print(f"⏭️ 活动 {lottery_id} 结果已由其他进程提交，跳过")
            return

        finalized = True
        print(f"✅ 开奖完成：{winners}")

        verify_url = (
            f"{settings.PUBLIC_HOST}/verify"
            f"?block={block_info.get('height', 0)}"
            f"&hash={block_info['hash']}"
            f"&lottery={lottery_id}"
        )
        announcement = build_draw_announcement(
            lottery, winners, block_info, verify_url
        )

        for target in (lottery.targets or []):
            try:
                await bot.send_message(
                    chat_id=target,
                    text=announcement,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                print(f"❌ 发送开奖公告到 {target} 失败: {e}")
                try:
                    await enqueue_retry(target, announcement)
                except Exception as retry_error:
                    print(f"❌ 开奖公告入重试队列失败: {retry_error}")

        for prize_name, user_ids in winners.items():
            for uid in user_ids:
                code = claim_codes.get((prize_name, uid), "")
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"🎉 <b>恭喜你中奖啦！</b>\n\n"
                            f"🏆 奖项：<b>{prize_name}</b>\n"
                            f"📌 活动：{lottery.title}\n"
                            f"🆔 活动 ID：<code>LK-{lottery_id}</code>\n"
                            f"🔑 核销码：<code>{code}</code>\n\n"
                            f"发送 /claim {code} 完成核销\n"
                            f"📄 <a href='{verify_url}'>查看区块链公证信息</a>"
                        ),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    print(f"通知中奖者 {uid} 失败: {e}")

    except Exception as e:
        print(f"❌ 开奖失败 (活动 {lottery.id}): {e}")
        if not finalized:
            print(
                f"📝 活动 {lottery_id} 保持 drawing，等待调度或再次触发后重试；"
                "已提交的结果不会回滚或重抽"
            )


def build_draw_announcement(lottery, winners, block_info, verify_url) -> str:
    text = "🎊 <b>开奖结果公布！</b>\n\n"
    text += f"📌 <b>{lottery.title}</b>\n\n"

    for prize_name, user_ids in winners.items():
        text += f"🏆 <b>{prize_name}</b>\n"
        for uid in user_ids:
            text += f"  👤 <a href='tg://user?id={uid}'>用户 {uid}</a>\n"
        text += "\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"

    if block_info.get("fallback"):
        text += "⚠️ 本次开奖使用备用随机源\n"
    else:
        text += f"⛓️ 区块高度：<code>{block_info['height']}</code>\n"
        text += f"🔑 区块哈希：<code>{block_info['hash'][:24]}...</code>\n"

    text += f'📄 <a href="{verify_url}">点击验证公平性</a>'
    return text


async def mark_ended(lottery_id: int, reason: str) -> bool:
    """仅在尚无开奖结果时结束活动，避免覆盖已提交的中奖名单。"""
    async with async_session() as db:
        result = await db.execute(
            update(Lottery)
            .where(
                Lottery.id == lottery_id,
                Lottery.status.in_([STATUS_ONGOING, STATUS_DRAWING]),
                Lottery.winner_list.is_(None),
            )
            .values(status=STATUS_ENDED, winner_list={"reason": reason})
        )
        await db.commit()
        updated = (result.rowcount or 0) > 0
    if updated:
        print(f"📝 活动 {lottery_id} 已标记结束：{reason}")
    else:
        print(f"⏭️ 活动 {lottery_id} 已有终态，跳过取消：{reason}")
    return updated


async def manual_draw(bot, lottery_id: int) -> dict:
    async with async_session() as db:
        lottery = (await db.execute(
            select(Lottery).where(Lottery.id == lottery_id)
        )).scalar_one_or_none()

    if not lottery:
        return {"ok": False, "msg": "活动不存在"}

    if lottery.status == STATUS_ENDED:
        return {"ok": False, "msg": f"活动状态为 {lottery.status}，无法开奖"}

    if lottery.status not in (STATUS_ONGOING, STATUS_DRAWING):
        return {"ok": False, "msg": f"活动状态为 {lottery.status}，无法开奖"}

    await execute_draw(bot, lottery)
    async with async_session() as db:
        status = (await db.execute(
            select(Lottery.status).where(Lottery.id == lottery_id)
        )).scalar_one_or_none()
    if status == STATUS_ENDED:
        return {"ok": True, "msg": "开奖完成"}
    return {"ok": False, "msg": "开奖尚未完成，可稍后重试"}
