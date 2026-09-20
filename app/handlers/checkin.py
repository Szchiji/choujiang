from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, date, timedelta
from sqlalchemy import select, update, func

from app.database import async_session
from app.models import UserMeta, Referral
from app.config import settings

router = Router()


@router.message(Command("checkin"))
async def checkin_cmd(message: types.Message):
    user_id = message.from_user.id
    today = date.today()

    async with async_session() as db:
        stmt = select(UserMeta).where(UserMeta.user_id == user_id)
        meta = (await db.execute(stmt)).scalar_one_or_none()

        if not meta:
            meta = UserMeta(user_id=user_id, extra_credits=0, sign_in_streak=0)
            db.add(meta)
            await db.commit()
            await db.refresh(meta)

        last = meta.last_sign_in.date() if meta.last_sign_in else None

        if last == today:
            await message.answer("📅 今天已经签到过啦，明天再来！")
            return

        # 连续签到判断
        if last == today - timedelta(days=1):
            streak = (meta.sign_in_streak or 0) + 1
        else:
            streak = 1

        # 奖励逻辑
        bonus = 1
        extra_msg = ""
        if streak % 7 == 0:
            bonus = 3
            extra_msg = "\n🎁 连续 7 天签到，额外奖励 +2 次！"
        if streak % 30 == 0:
            bonus = 10
            extra_msg = "\n🏆 连续 30 天签到，额外奖励 +7 次！"

        meta.sign_in_streak = streak
        meta.last_sign_in = datetime.now()
        meta.extra_credits = (meta.extra_credits or 0) + bonus
        await db.commit()

    await message.answer(
        f"✅ 签到成功！\n\n"
        f"🔥 连续签到：{streak} 天\n"
        f"🎁 本次奖励：+{bonus} 次抽奖机会{extra_msg}\n\n"
        f"💡 明天再来可以保持连续记录！"
    )


@router.message(Command("invite"))
async def invite_cmd(message: types.Message):
    """生成专属邀请链接"""
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    async with async_session() as db:
        stmt = select(UserMeta).where(UserMeta.user_id == user_id)
        meta = (await db.execute(stmt)).scalar_one_or_none()
        count = meta.referral_count if meta else 0

    await message.answer(
        f"🎁 <b>邀请好友，双方各得 1 次抽奖机会</b>\n\n"
        f"🔗 你的专属邀请链接：\n"
        f"<code>{invite_link}</code>\n\n"
        f"📊 已成功邀请：<b>{count}</b> 人\n\n"
        f"💡 好友通过链接启动机器人后，双方自动获得奖励。",
        parse_mode="HTML",
    )


async def process_referral(bot, inviter_id: int, invitee_id: int):
    """处理邀请奖励（在 /start 时触发）"""
    if inviter_id == invitee_id:
        return False

    async with async_session() as db:
        # 防止重复
        stmt = select(Referral).where(Referral.invitee_id == invitee_id)
        exists = (await db.execute(stmt)).scalar_one_or_none()
        if exists:
            return False

        # 记录邀请
        db.add(Referral(inviter_id=inviter_id, invitee_id=invitee_id))

        # 邀请人 +1
        inviter_meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == inviter_id)
        )).scalar_one_or_none()
        if not inviter_meta:
            inviter_meta = UserMeta(user_id=inviter_id, extra_credits=0, referral_count=0)
            db.add(inviter_meta)
        inviter_meta.extra_credits = (inviter_meta.extra_credits or 0) + 1
        inviter_meta.referral_count = (inviter_meta.referral_count or 0) + 1

        # 被邀请人 +1
        invitee_meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == invitee_id)
        )).scalar_one_or_none()
        if not invitee_meta:
            invitee_meta = UserMeta(user_id=invitee_id, extra_credits=0)
            db.add(invitee_meta)
        invitee_meta.extra_credits = (invitee_meta.extra_credits or 0) + 1

        await db.commit()

    # 通知双方
    try:
        await bot.send_message(
            inviter_id,
            "🎉 有好友通过你的邀请链接加入！\n✅ 你获得 +1 次抽奖机会。"
        )
        await bot.send_message(
            invitee_id,
            "🎉 欢迎加入！通过好友邀请，你获得 +1 次抽奖机会。"
        )
    except Exception:
        pass

    return True
