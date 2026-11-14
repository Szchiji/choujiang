from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select, func, desc

from app.config import settings
from app.database import async_session
from app.models import UserMeta, Lottery, Participant, CloneApplication, Bot

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "<b>🛠️ 管理员面板</b>\n\n"
        "/stats - 查看平台统计\n"
        "/pending - 查看待审核克隆申请\n"
        "/broadcast <内容> - 广播消息给所有用户\n"
        "/approve <订单ID> - 批准订单",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    async with async_session() as db:
        users = (await db.execute(select(func.count(UserMeta.user_id)))).scalar() or 0
        lotteries = (await db.execute(select(func.count(Lottery.id)))).scalar() or 0
        ongoing = (await db.execute(
            select(func.count(Lottery.id)).where(Lottery.status == "ongoing")
        )).scalar() or 0
        participants = (await db.execute(select(func.count(Participant.id)))).scalar() or 0
        bots = (await db.execute(
            select(func.count(Bot.id)).where(Bot.is_master == False, Bot.is_active == True)
        )).scalar() or 0
        pending_orders = (await db.execute(
            select(func.count(CloneApplication.id)).where(CloneApplication.status == "paid")
        )).scalar() or 0

    await message.answer(
        "<b>📊 平台统计</b>\n\n"
        f"👥 用户数：<b>{users}</b>\n"
        f"🎯 抽奖活动：<b>{lotteries}</b>（进行中 {ongoing}）\n"
        f"👥 累计参与：<b>{participants}</b>\n"
        f"🤖 活跃子号：<b>{bots}</b>\n"
        f"💰 待处理订单：<b>{pending_orders}</b>",
        parse_mode="HTML",
    )


@router.message(Command("pending"))
async def pending_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    async with async_session() as db:
        rows = (await db.execute(
            select(CloneApplication)
            .where(CloneApplication.status == "paid")
            .order_by(desc(CloneApplication.created_at))
            .limit(20)
        )).scalars().all()

    if not rows:
        await message.answer("✅ 暂无待处理订单")
        return

    text = "<b>📋 待处理订单</b>\n\n"
    for o in rows:
        text += (
            f"🆔 <code>#{o.id}</code>\n"
            f"   👤 用户：<code>{o.user_id}</code>\n"
            f"   📦 套餐：{o.plan}\n"
            f"   📅 {o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else ''}\n\n"
        )
    text += "使用 /approve <订单ID> 批准"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("approve"))
async def approve_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("用法：/approve <订单ID>")
        return

    order_id = int(args[1])
    async with async_session() as db:
        app_row = (await db.execute(
            select(CloneApplication).where(CloneApplication.id == order_id)
        )).scalar_one_or_none()

        if not app_row:
            await message.answer("❌ 订单不存在")
            return

        if app_row.status != "paid":
            await message.answer(f"❌ 订单状态为 {app_row.status}，无法批准")
            return

        from datetime import datetime, timedelta
        app_row.status = "approved"
        app_row.processed_at = datetime.now()

        existing = (await db.execute(
            select(Bot).where(Bot.owner_id == app_row.user_id, Bot.is_master == False)
        )).scalar_one_or_none()

        if not existing:
            days = {"monthly": 30, "yearly": 365, "lifetime": 36500}.get(app_row.plan, 30)
            db.add(Bot(
                owner_id=app_row.user_id,
                bot_token=app_row.bot_token or f"placeholder_{app_row.user_id}",
                bot_username=app_row.bot_name or f"clone_{app_row.user_id}",
                is_master=False,
                is_active=True,
                expire_time=datetime.now() + timedelta(days=days),
            ))

        await db.commit()

    await message.answer(f"✅ 订单 #{order_id} 已批准")

    try:
        await message.bot.send_message(
            app_row.user_id,
            "🎉 <b>您的克隆申请已通过！</b>\n\n"
            "管理员已为您开通子号权限。\n"
            "请联系管理员获取专属机器人链接。",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("用法：/broadcast <广播内容>")
        return

    content = args[1]
    async with async_session() as db:
        users = (await db.execute(select(UserMeta.user_id))).scalars().all()

    sent = 0
    failed = 0
    for uid in users:
        try:
            await message.bot.send_message(uid, content, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"✅ 广播完成：成功 {sent}，失败 {failed}")
