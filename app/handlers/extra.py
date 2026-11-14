"""模板、排行榜、核销相关命令"""
from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select, desc, func
import secrets

from app.database import async_session
from app.models import LotteryTemplate, UserMeta, PrizeClaim, Lottery

router = Router()


@router.message(Command("templates"))
async def list_templates(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as db:
        rows = (await db.execute(
            select(LotteryTemplate)
            .where(LotteryTemplate.owner_id == user_id)
            .order_by(desc(LotteryTemplate.created_at))
            .limit(10)
        )).scalars().all()

    if not rows:
        await message.answer("📭 暂无模板。创建抽奖后可使用 /savetpl <名称> 保存。")
        return

    text = "<b>📋 我的抽奖模板</b>\n\n"
    for t in rows:
        text += f"• <b>{t.name}</b> (ID: {t.id})\n"
    text += "\n使用 /usetpl <ID> 加载模板到创建页"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("leaderboard"))
async def leaderboard(message: types.Message):
    async with async_session() as db:
        rows = (await db.execute(
            select(UserMeta)
            .where(UserMeta.referral_count > 0)
            .order_by(desc(UserMeta.referral_count))
            .limit(10)
        )).scalars().all()

    if not rows:
        await message.answer("📊 暂无邀请排行数据")
        return

    text = "<b>🏆 邀请排行榜</b>\n\n"
    for i, u in enumerate(rows, 1):
        text += f"{i}. <code>{u.user_id}</code> — {u.referral_count} 人\n"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("claim"))
async def claim_prize(message: types.Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("用法：/claim <核销码>")
        return

    code = args[1].strip().upper()
    async with async_session() as db:
        claim = (await db.execute(
            select(PrizeClaim).where(PrizeClaim.claim_code == code)
        )).scalar_one_or_none()

        if not claim:
            await message.answer("❌ 核销码不存在")
            return

        if claim.claimed:
            await message.answer("✅ 该奖品已核销")
            return

        from datetime import datetime
        claim.claimed = True
        claim.claimed_at = datetime.now()
        await db.commit()

    await message.answer(
        f"🎉 <b>核销成功！</b>\n\n"
        f"奖品：{claim.prize_name}\n"
        f"活动 ID：LK-{claim.lottery_id}",
        parse_mode="HTML",
    )
