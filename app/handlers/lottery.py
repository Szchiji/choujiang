from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Lottery
from app.channel_checker import check_channels, build_channel_links

router = Router()


def miniapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 打开 Mini App 创建",
                    web_app=WebAppInfo(url=f"{settings.PUBLIC_HOST}/app"),
                )
            ]
        ]
    )


@router.message(Command("create"))
async def create_cmd(message: types.Message):
    await message.reply(
        "📝 点击下方按钮打开 Mini App 创建抽奖\n\n"
        "💡 支持多奖品、多目标发布、区块链公证开奖",
        parse_mode="HTML",
        reply_markup=miniapp_keyboard(),
    )


@router.message(Command("my"))
async def my_lotteries(message: types.Message):
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
        await message.answer(
            "📭 你还没有创建过抽奖活动。",
            reply_markup=miniapp_keyboard(),
        )
        return

    text = "📋 <b>我创建的抽奖</b>\n\n"
    for lot in rows:
        status_icon = {
            "ongoing": "🟢", "drawing": "🟡", "ended": "🔴", "draft": "⚪",
        }.get(lot.status, "⚪")
        text += f"{status_icon} <b>{lot.title}</b>\n"
        text += f"   🆔 <code>LK-{lot.id}</code> · 状态：{lot.status}\n\n"

    await message.answer(text, parse_mode="HTML", reply_markup=miniapp_keyboard())


@router.callback_query(lambda c: c.data.startswith("join_"))
async def join_lottery(callback: types.CallbackQuery):
    try:
        lottery_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ 无效的抽奖", show_alert=True)
        return

    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.full_name

    async with async_session() as db:
        lottery = (await db.execute(
            select(Lottery).where(Lottery.id == lottery_id)
        )).scalar_one_or_none()

        if not lottery:
            await callback.answer("❌ 活动不存在或已删除", show_alert=True)
            return

        if lottery.status != "ongoing":
            await callback.answer("⏹️ 该活动已结束或正在开奖", show_alert=True)
            return

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

    from app.lottery_service import try_add_participant
    status, count = await try_add_participant(lottery_id, user_id, username)
    if status == "not_found":
        await callback.answer("❌ 活动不存在或已删除", show_alert=True)
        return
    if status == "ended":
        await callback.answer("⏹️ 该活动已结束或正在开奖", show_alert=True)
        return
    if status == "already":
        await callback.answer("✅ 你已经参与过了，请耐心等待开奖", show_alert=True)
        return

    if lottery.draw_mode == "count" and lottery.target_count:
        if count >= lottery.target_count:
            import asyncio
            asyncio.create_task(_trigger_draw(callback.bot, lottery_id))

    await callback.answer(
        f"✅ 参与成功！\n当前参与人数：{count} 人\n祝你好运 🍀",
        show_alert=True,
    )


async def _trigger_draw(bot, lottery_id: int):
    from app.lottery_service import execute_draw
    from app.database import async_session
    async with async_session() as db:
        lottery = (await db.execute(
            select(Lottery).where(Lottery.id == lottery_id)
        )).scalar_one_or_none()
        if lottery:
            await execute_draw(bot, lottery)
