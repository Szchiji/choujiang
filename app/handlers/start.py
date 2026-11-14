from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select

from app.config import settings
from app.handlers.checkin import process_referral
from app.database import async_session
from app.models import Bot

router = Router()


def miniapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 打开 Mini App",
                    web_app=WebAppInfo(url=f"{settings.PUBLIC_HOST}/app"),
                )
            ]
        ]
    )


@router.message(Command("start"))
async def start_cmd(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    payload = command.args or ""

    if payload.startswith("ref_"):
        try:
            inviter_id = int(payload.replace("ref_", ""))
            await process_referral(message.bot, inviter_id, user_id)
        except (ValueError, Exception) as e:
            print(f"处理邀请失败: {e}")

    welcome = None
    try:
        me = await message.bot.get_me()
        async with async_session() as db:
            bot_row = (await db.execute(
                select(Bot).where(Bot.bot_username == me.username)
            )).scalar_one_or_none()
            if bot_row and bot_row.custom_welcome:
                welcome = bot_row.custom_welcome
    except Exception:
        pass

    text = welcome or (
        "🎯 欢迎使用 <b>LuckyDraw Cloud</b>！\n\n"
        "点击下方按钮打开 Mini App，创建抽奖、查看广场、管理账户。\n\n"
        "📖 <b>常用命令</b>\n"
        "/create - 打开 Mini App\n"
        "/checkin - 每日签到\n"
        "/invite - 邀请好友\n"
        "/my - 我的抽奖\n"
        "/help - 帮助"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=miniapp_keyboard())


@router.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "<b>📖 命令列表</b>\n\n"
        "/start - 欢迎 + Mini App\n"
        "/create - 打开 Mini App 创建抽奖\n"
        "/checkin - 每日签到领次数\n"
        "/invite - 邀请好友得奖励\n"
        "/my - 查看我创建的抽奖\n"
        "/me - 查看我的账户\n"
        "/buy - 购买付费套餐\n"
        "/orders - 我的订单\n"
        "/dashboard - 数据看板",
        parse_mode="HTML",
        reply_markup=miniapp_keyboard(),
    )
