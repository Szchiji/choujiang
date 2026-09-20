from datetime import datetime

from sqlalchemy import select, update

from app.database import async_session
from app.models import Lottery, Participant
from app.blockchain import get_latest_block_hash, draw_winners
from app.channel_checker import check_channels_for_draw
from app.config import settings


# ==================== 数据查询 ====================

async def get_due_lotteries() -> list:
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


async def get_participants(lottery_id: int) -> list:
    """获取参与用户 ID 列表"""
    async with async_session() as db:
        stmt = select(Participant.user_id).where(
            Participant.lottery_id == lottery_id
        )
        result = await db.execute(stmt)
        return [row[0] for row in result.all()]


async def get_participant_count(lottery_id: int) -> int:
    """获取参与人数"""
    async with async_session() as db:
        stmt = select(Participant).where(Participant.lottery_id == lottery_id)
        result = await db.execute(stmt)
        return len(list(result.scalars().all()))


# ==================== 开奖主流程 ====================

async def execute_draw(bot, lottery):
    """
    执行单个活动的开奖：
    1. 获取参与者
    2. 过滤已取关频道的用户
    3. 获取比特币区块哈希
    4. 执行抽奖算法
    5. 保存结果 + 发布公告
    """
    try:
        lottery_id = lottery.id
        print(f"🎯 开始开奖：{lottery.title} (ID: {lottery_id})")

        # ===== 1. 获取参与者 =====
        participants = await get_participants(lottery_id)
        if not participants:
            await mark_ended(lottery_id, "参与人数为 0，自动取消")
            print(f"⚠️ 活动 {lottery_id} 无参与者，取消开奖")
            return

        # ===== 2. 开奖前二次校验频道关注 =====
        channels = lottery.channels or []
        if channels:
            valid = []
            for uid in participants:
                try:
                    if await check_channels_for_draw(bot, uid, channels):
                        valid.append(uid)
                except Exception as e:
                    print(f"校验用户 {uid} 频道失败: {e}")

            print(f"⚠️ 开奖前过滤：{len(participants)} → {len(valid)} 人（已剔除取关用户）")
            participants = valid

        if not participants:
            await mark_ended(lottery_id, "所有参与者已取关，取消开奖")
            return

        # ===== 3. 校验奖品数 =====
        prizes = lottery.prizes or []
        total_prizes = sum(p.get("count", 0) for p in prizes)
        if len(participants) < total_prizes:
            await mark_ended(
                lottery_id,
                f"有效参与人数({len(participants)})少于奖品总数({total_prizes})，取消开奖",
            )
            return

        # ===== 4. 获取比特币区块哈希 =====
        try:
            block_info = await get_latest_block_hash()
        except Exception as e:
            print(f"❌ 获取区块链哈希失败: {e}")
            # 降级方案：使用系统时间 + 随机数作为备用种子
            import hashlib
            import time
            fake_seed = hashlib.sha256(f"{lottery_id}_{time.time()}".encode()).hexdigest()
            block_info = {
                "height": 0,
                "hash": fake_seed,
                "fallback": True,
            }

        # ===== 5. 执行抽奖算法 =====
        winners = draw_winners(
            participants=participants,
            prizes=prizes,
            block_hash=block_info["hash"],
            lottery_id=lottery_id,
        )
        if not winners:
            await mark_ended(lottery_id, "抽奖算法返回空结果，取消开奖")
            return

        # ===== 6. 保存开奖结果 =====
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

        # ===== 7. 向所有目标发布开奖公告 =====
        verify_url = (
            f"{settings.PUBLIC_HOST}/verify"
            f"?block={block_info.get('height', 0)}"
            f"&hash={block_info['hash']}"
            f"&lottery={lottery_id}"
        )
        announcement = build_draw_announcement(
            lottery, winners, block_info, verify_url
        )

        targets = lottery.targets or []
        for target in targets:
            try:
                await bot.send_message(
                    chat_id=target,
                    text=announcement,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                print(f"✅ 开奖公告已发送到 {target}")
            except Exception as e:
                print(f"❌ 发送开奖公告到 {target} 失败: {e}")

        # ===== 8. 私聊通知中奖者 =====
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
                            f"📄 <a href='{verify_url}'>查看区块链公证信息</a>\n\n"
                            f"请耐心等待主办方发放奖品。"
                        ),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    print(f"通知中奖者 {uid} 失败: {e}")

    except Exception as e:
        print(f"❌ 开奖失败 (活动 {lottery.id}): {e}")
        await mark_ended(lottery.id, f"开奖异常: {str(e)}")


# ==================== 辅助函数 ====================

def build_draw_announcement(lottery, winners, block_info, verify_url) -> str:
    """构建开奖公告消息（HTML 格式）"""
    text = "🎊 <b>开奖结果公布！</b>\n\n"
    text += f"📌 <b>{lottery.title}</b>\n\n"

    for prize_name, user_ids in winners.items():
        text += f"🏆 <b>{prize_name}</b>\n"
        for uid in user_ids:
            text += f"  👤 <a href='tg://user?id={uid}'>用户 {uid}</a>\n"
        text += "\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"

    if block_info.get("fallback"):
        text += "⚠️ 本次开奖使用备用随机源（区块链 API 暂不可用）\n"
    else:
        text += f"⛓️ 区块高度：<code>{block_info['height']}</code>\n"
        text += f"🔑 区块哈希：<code>{block_info['hash'][:24]}...</code>\n"

    text += f'📄 <a href="{verify_url}">点击验证公平性</a>'
    return text


async def mark_ended(lottery_id: int, reason: str):
    """标记活动为已结束"""
    async with async_session() as db:
        await db.execute(
            update(Lottery)
            .where(Lottery.id == lottery_id)
            .values(status="ended", winner_list={"reason": reason})
        )
        await db.commit()
    print(f"📝 活动 {lottery_id} 已标记结束：{reason}")


# ==================== 手动开奖（管理员用） ====================

async def manual_draw(bot, lottery_id: int) -> dict:
    """管理员手动触发开奖"""
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
