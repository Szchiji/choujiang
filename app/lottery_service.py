from datetime import datetime

from sqlalchemy import select, update

from app.database import async_session
from app.models import Lottery, Participant
from app.blockchain import get_latest_block_hash, draw_winners
from app.channel_checker import check_channels_for_draw
from app.config import settings


async def get_due_lotteries() -> list:
    async with async_session() as db:
        now = datetime.now()
        stmt = select(Lottery).where(
            Lottery.status == "ongoing",
            Lottery.draw_mode == "time",
            Lottery.draw_time <= now,
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
        stmt = select(Participant).where(Participant.lottery_id == lottery_id)
        result = await db.execute(stmt)
        return len(list(result.scalars().all()))


async def execute_draw(bot, lottery):
    try:
        lottery_id = lottery.id
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

        async with async_session() as db:
            await db.execute(
                update(Lottery)
                .where(Lottery.id == lottery_id)
                .values(
                    winner_list=winners,
                    block_hash=block_info["hash"],
                    block_height=block_info.get("height", 0),
                    status="ended",
                )
            )
            await db.commit()

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

        for prize_name, user_ids in winners.items():
            for uid in user_ids:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"🎉 <b>恭喜你中奖啦！</b>\n\n"
                            f"🏆 奖项：<b>{prize_name}</b>\n"
                            f"📌 活动：{lottery.title}\n"
                            f"🆔 活动 ID：<code>LK-{lottery_id}</code>\n\n"
                            f"📄 <a href='{verify_url}'>查看区块链公证信息</a>"
                        ),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    print(f"通知中奖者 {uid} 失败: {e}")

    except Exception as e:
        print(f"❌ 开奖失败 (活动 {lottery.id}): {e}")
        await mark_ended(lottery.id, f"开奖异常: {str(e)}")


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


async def mark_ended(lottery_id: int, reason: str):
    async with async_session() as db:
        await db.execute(
            update(Lottery)
            .where(Lottery.id == lottery_id)
            .values(status="ended", winner_list={"reason": reason})
        )
        await db.commit()
    print(f"📝 活动 {lottery_id} 已标记结束：{reason}")


async def manual_draw(bot, lottery_id: int) -> dict:
    async with async_session() as db:
        lottery = (await db.execute(
            select(Lottery).where(Lottery.id == lottery_id)
        )).scalar_one_or_none()

    if not lottery:
        return {"ok": False, "msg": "活动不存在"}

    if lottery.status != "ongoing":
        return {"ok": False, "msg": f"活动状态为 {lottery.status}，无法开奖"}

    await execute_draw(bot, lottery)
    return {"ok": True, "msg": "开奖完成"}
