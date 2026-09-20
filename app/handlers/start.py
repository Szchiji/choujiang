from aiogram import Router, types
from aiogram.filters import Command

router = Router()


@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎯 欢迎使用 <b>LuckyDraw Cloud</b>！\n\n"
        "免费版每日可创建 1 次抽奖。\n"
        "发送 /create 开始创建你的抽奖活动。\n\n"
        "💡 使用 /help 查看所有命令。",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "<b>📖 命令列表</b>\n\n"
        "/start - 欢迎信息\n"
        "/create - 创建抽奖（返回 Web 链接）\n"
        "/my - 查看我创建的抽奖\n"
        "/clone - 申请克隆专属机器人\n",
        parse_mode="HTML",
    )
