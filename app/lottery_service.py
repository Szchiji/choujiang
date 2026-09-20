from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Lottery, Participant, Bot
from app.blockchain import get_latest_block_hash, draw_winners
from app.message_builder import build_lottery_message
from app.config import settings


async def get_due_lotteries() -> list[Lottery]:
    """获取所有到达开奖时间的活动"""
    async with async_session() as db:
        now = datetime.now()
        stmt = select(Lottery).where(
            Lottery.status == "ongoing",
            Lottery.draw_mode == "time",
            Lottery.draw_time <= now,
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_participants(lottery_id: int) -> list[int]:
    """获取参与用户 ID 列表"""
    async with async_session() as db:
        stmt = select(Participant.user_id).where(Participant.lottery_id == lottery_id)
        result = await db.execute(stmt)
        return [row[0] for row in result.all()]


async def execute_draw(bot, lottery: Lottery):
    """执行单个活动的开奖"""
    try:
        # 1. 获取参与者
        participants = await get_participants(lottery.id)
        if not participants:
            await mark_ended(lottery.id, "参与人数为0，自动取消")
            return

        # 2. 获取区块链哈希
        block_info = await get_latest_block_hash()

        # 3. 执行抽奖
        prizes = lottery.prizes or []
        winners = draw_winners(
            participants=participants,
            prizes=prizes,
            block_hash=block_info["hash"],
            lottery_id=lottery.id,
        )
        if not winners:
            await mark_ended(lottery.id, "参与人数少于奖品数，取消开奖")
            return

        # 4. 保存结果
        async with async_session() as db:
            await db.execute(
                update(Lottery)
                .where(Lottery.id == lottery.id)
                .values(
                    winner_list=winners,
                    block_hash=block_info["hash"],
                    block_height=block_info["height"],
                    status="ended",
                )
            )
            await db.commit()

        # 5. 向所有目标发布开奖公告
        verify_url = f"{settings.PUBLIC_HOST}/verify?block={block_info['height']}&hash={block_info['hash']}&lottery={lottery.id}"
        announcement = build_draw_announcement(lottery, winners, block_info, verify_url)

        for target in (lottery.targets or []):
            try:
                await bot.send_message(
                    chat_id=target,
                    text=announcement,
                    parse_mode="HTML",
                )
            except Exception as e:
                print(f"发送开奖公告到 {target} 失败: {e}")

    except Exception as e:
        print(f"❌ 开奖失败 (活动 {lottery.id}): {e}")
        await mark_ended(lottery.id, f"开奖异常: {e}")


def build_draw_announcement(lottery, winners, block_info, verify_url):
    """构建开奖公告消息"""
    text = f"🎊 <b>开奖结果公布！</b>\n\n"
    text += f"📌 {lottery.title}\n\n"
    for prize_name, user_ids in winners.items():
        text += f"🏆 <b>{prize_name}</b>\n"
        for uid in user_ids:
            text += f"  👤 <a href='tg://user?id={uid}'>用户{uid}</a>\n"
        text += "\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
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
