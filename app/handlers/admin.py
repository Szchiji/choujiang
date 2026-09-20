from aiogram import Router, types
from aiogram.filters import Command
from app.config import settings

router = Router()


@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id not in settings.admin_ids_list:
        return
    await message.answer(
        "<b>🛠️ 管理员面板</b>\n\n"
        "/stats - 查看平台统计\n"
        "/pending - 查看待审核克隆申请\n"
        "/broadcast - 广播消息\n",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    if message.from_user.id not in settings.admin_ids_list:
        return
    await message.answer("📊 统计功能开发中...")
