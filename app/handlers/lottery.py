from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from urllib.parse import urlencode
from sqlalchemy import select, func

from app.config import settings
from app.database import async_session
from app.models import Lottery, Participant, UserMeta
from app.channel_checker import check_channels, build_channel_links

router = Router()


@router.message(Command("create"))
async def create_cmd(message: types.Message):
    """用户发送 /create，返回 Web 创建链接"""
    user_id = message.from_user.id

    # 检查用户今日是否还有配额
    async with async_session() as db:
        meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == user_id)
        )).scalar_one_or_none()

    # 免费版每日 1 次，付费用户由 Web 后台校验
    params = urlencode({"uid": user_id})
    create_url = f"{settings.PUBLIC_HOST}/create?{params}"

    await message.reply(
        f"📝 点击下方链接创建抽奖：\n\n"
        f'🔗 <a href="{create_url}">打开创建后台</a>\n\n'
        f"💡 支持多奖品、多目标发布、区块链公证开奖",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("my"))
async def my_lotteries(message: types.Message):
    """查看用户创建的抽奖"""
    user_id = message.from_user.id
    async with async_session() as db:
        stmt = (
            select(Lottery)
            .where(Lottery.bot_id == user_id)
            .order_by(Lottery.created_at.desc())
            .limit(10)
        )
        rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        await message.answer("📭 你还没有创建过抽奖活动。\n发送 /create 开始创建！")
        return

    text = "📋 <b>我创建的抽奖</b>\n\n"
    for lot in rows:
        status_icon = {
            "ongoing": "🟢", "ended": "🔴", "draft": "⚪",
        }.get(lot.status, "⚪")
        text += f"{status_icon} <b>{lot.title}</b>\n"
        text += f"   🆔 <code>LK-{lot.id}</code> · 状态：{lot.status}\n\n"

    await message.answer(text, parse_mode="HTML")


@router.callback_query(lambda c: c.data.startswith("join_"))
async def join_lottery(callback: types.CallbackQuery):
    """用户点击"参与抽奖"按钮"""
    try:
        lottery_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ 无效的抽奖", show_alert=True)
        return

    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.full_name

    # ===== 1. 读取活动 =====
    async with async_session() as db:
        lottery = (await db.execute(
            select(Lottery).where(Lottery.id == lottery_id)
        )).scalar_one_or_none()

        if not lottery:
            await callback.answer("❌ 活动不存在或已删除", show_alert=True)
            return

        if lottery.status != "ongoing":
            await callback.answer("⏹️ 该活动已结束", show_alert=True)
            return

        # ===== 2. 检查是否已参与 =====
        exists = (await db.execute(
            select(Participant).where(
                Participant.lottery_id == lottery_id,
                Participant.user_id == user_id,
            )
        )).scalar_one_or_none()

        if exists:
            await callback.answer("✅ 你已经参与过了，请耐心等待开奖", show_alert=True)
            return

    # ===== 3. 校验强制关注频道 =====
    channels = lottery.channels or []
    if channels:
        result = await check_channels(callback.bot, user_id, channels)
        if not result["ok"]:
            links = build_channel_links(result["failed"])
            await callback.answer(
                f"❌ 请先关注以下频道再参与：\n\n{links}",
                show_alert=True,
            )
            return

    # ===== 4. 写入参与记录 =====
    async with async_session() as db:
        db.add(Participant(
            lottery_id=lottery_id,
            user_id=user_id,
            username=username,
        ))
        await db.commit()

        # ===== 5. 更新参与人数 + 满员自动开奖 =====
        count = (await db.execute(
            select(func.count(Participant.id)).where(
                Participant.lottery_id == lottery_id
            )
        )).scalar() or 0

    # ===== 6. 满员触发开奖 =====
    if lottery.draw_mode == "count" and lottery.target_count:
        if count >= lottery.target_count:
            # 异步触发开奖，不阻塞用户响应
            import asyncio
            from app.lottery_service import execute_draw
            asyncio.create_task(_trigger_draw(callback.bot, lottery_id))

    await callback.answer(
        f"✅ 参与成功！\n当前参与人数：{count} 人\n祝你好运 🍀",
        show_alert=True,
    )


async def _trigger_draw(bot, lottery_id: int):
    """触发开奖（后台任务）"""
    from app.lottery_service import execute_draw
    from app.database import async_session
    async with async_session() as db:
        lottery = (await db.execute(
            select(Lottery).where(Lottery.id == lottery_id)
        )).scalar_one_or_none()
        if lottery and lottery.status == "ongoing":
            await execute_draw(bot, lottery)
