from aiogram import Router, types, Bot
from aiogram.filters import Command
from datetime import datetime, date, timedelta
from sqlalchemy import select, func

from app.database import async_session
from app.models import UserMeta, Referral

router = Router()


# ==================== 签到 ====================

@router.message(Command("checkin"))
async def checkin_cmd(message: types.Message):
    """每日签到，连续签到额外奖励"""
    user_id = message.from_user.id
    today = date.today()

    async with async_session() as db:
        meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == user_id)
        )).scalar_one_or_none()

        # 首次使用，自动创建记录
        if not meta:
            meta = UserMeta(
                user_id=user_id,
                extra_credits=0,
                sign_in_streak=0,
                free_quota=1,
            )
            db.add(meta)
            await db.commit()
            await db.refresh(meta)

        last = meta.last_sign_in.date() if meta.last_sign_in else None

        # 今日已签到
        if last == today:
            await message.answer(
                f"📅 今天已经签到过啦！\n\n"
                f"🔥 连续签到：<b>{meta.sign_in_streak}</b> 天\n"
                f"🎁 累计额外次数：<b>{meta.extra_credits}</b>\n\n"
                f"明天再来保持连续记录！",
                parse_mode="HTML",
            )
            return

        # 判断连续签到
        if last == today - timedelta(days=1):
            streak = (meta.sign_in_streak or 0) + 1
        else:
            streak = 1

        # 奖励规则
        bonus = 1
        extra_msg = ""
        if streak % 30 == 0:
            bonus = 10
            extra_msg = "\n🏆 <b>连续 30 天签到</b>，额外奖励 +7 次！"
        elif streak % 7 == 0:
            bonus = 3
            extra_msg = "\n🎁 <b>连续 7 天签到</b>，额外奖励 +2 次！"

        meta.sign_in_streak = streak
        meta.last_sign_in = datetime.now()
        meta.extra_credits = (meta.extra_credits or 0) + bonus
        await db.commit()

    await message.answer(
        f"✅ <b>签到成功！</b>\n\n"
        f"🔥 连续签到：<b>{streak}</b> 天\n"
        f"🎁 本次奖励：<b>+{bonus}</b> 次抽奖机会{extra_msg}\n\n"
        f"💡 发送 /create 使用抽奖次数",
        parse_mode="HTML",
    )


# ==================== 邀请裂变 ====================

@router.message(Command("invite"))
async def invite_cmd(message: types.Message):
    """生成专属邀请链接"""
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    async with async_session() as db:
        meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == user_id)
        )).scalar_one_or_none()
        count = meta.referral_count if meta else 0
        credits = meta.extra_credits if meta else 0

    await message.answer(
        f"🎁 <b>邀请好友，双方各得 1 次抽奖机会</b>\n\n"
        f"🔗 <b>你的专属邀请链接：</b>\n"
        f"<code>{invite_link}</code>\n\n"
        f"📊 已成功邀请：<b>{count}</b> 人\n"
        f"🎫 当前额外次数：<b>{credits}</b> 次\n\n"
        f"💡 <b>使用方法：</b>\n"
        f"复制上方链接，发送给好友或分享到群组。\n"
        f"好友点击链接启动机器人后，双方自动获得 +1 次抽奖机会。",
        parse_mode="HTML",
    )


async def process_referral(bot: Bot, inviter_id: int, invitee_id: int) -> bool:
    """
    处理邀请奖励（在 /start 时触发）
    返回 True 表示处理成功，False 表示重复或无效
    """
    # 防止自我邀请
    if inviter_id == invitee_id:
        return False

    async with async_session() as db:
        # 防止重复邀请
        exists = (await db.execute(
            select(Referral).where(Referral.invitee_id == invitee_id)
        )).scalar_one_or_none()
        if exists:
            return False

        # 记录邀请关系
        db.add(Referral(inviter_id=inviter_id, invitee_id=invitee_id))

        # === 邀请人奖励 ===
        inviter_meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == inviter_id)
        )).scalar_one_or_none()
        if not inviter_meta:
            inviter_meta = UserMeta(
                user_id=inviter_id, extra_credits=0, referral_count=0, free_quota=1
            )
            db.add(inviter_meta)
        inviter_meta.extra_credits = (inviter_meta.extra_credits or 0) + 1
        inviter_meta.referral_count = (inviter_meta.referral_count or 0) + 1

        # === 被邀请人奖励 ===
        invitee_meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == invitee_id)
        )).scalar_one_or_none()
        if not invitee_meta:
            invitee_meta = UserMeta(user_id=invitee_id, extra_credits=0, free_quota=1)
            db.add(invitee_meta)
        invitee_meta.extra_credits = (invitee_meta.extra_credits or 0) + 1

        await db.commit()

    # 通知双方
    try:
        await bot.send_message(
            inviter_id,
            "🎉 <b>邀请成功！</b>\n\n"
            "有好友通过你的邀请链接加入了机器人。\n"
            "✅ 你获得 <b>+1 次抽奖机会</b>！",
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"通知邀请人 {inviter_id} 失败: {e}")

    try:
        await bot.send_message(
            invitee_id,
            "🎉 <b>欢迎加入 LuckyDraw Cloud！</b>\n\n"
            "通过好友邀请，你获得 <b>+1 次抽奖机会</b>！\n\n"
            "📖 使用 /help 查看所有命令",
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"通知被邀请人 {invitee_id} 失败: {e}")

    return True


# ==================== 我的信息 ====================

@router.message(Command("me"))
async def me_cmd(message: types.Message):
    """查看个人配额和签到状态"""
    user_id = message.from_user.id

    async with async_session() as db:
        meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == user_id)
        )).scalar_one_or_none()

    if not meta:
        await message.answer(
            "📭 你还没有使用过 LuckyDraw Cloud。\n发送 /create 开始创建抽奖！"
        )
        return

    trial_status = "❌ 未开始"
    if meta.trial_end:
        if meta.trial_end > datetime.now():
            days = (meta.trial_end - datetime.now()).days
            trial_status = f"🟢 试用中（剩 {days} 天）"
        else:
            trial_status = "🔴 已结束"

    await message.answer(
        f"👤 <b>我的账户</b>\n\n"
        f"🆔 User ID：<code>{user_id}</code>\n"
        f"🔥 连续签到：<b>{meta.sign_in_streak or 0}</b> 天\n"
        f"🎫 额外次数：<b>{meta.extra_credits or 0}</b> 次\n"
        f"📅 每日免费：<b>{meta.free_quota or 1}</b> 次\n"
        f"👥 邀请人数：<b>{meta.referral_count or 0}</b> 人\n"
        f"🎁 试用状态：{trial_status}",
        parse_mode="HTML",
    )
