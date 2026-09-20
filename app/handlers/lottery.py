from aiogram import Router, types
from aiogram.filters import Command
from urllib.parse import urlencode
from app.config import settings

router = Router()


@router.message(Command("create"))
async def create_cmd(message: types.Message):
    user_id = message.from_user.id
    params = urlencode({"uid": user_id})
    create_url = f"{settings.PUBLIC_HOST}/create?{params}"
    await message.reply(
        f"📝 点击下方链接创建抽奖：\n\n"
        f'🔗 <a href="{create_url}">打开创建后台</a>\n\n'
        f"💡 支持多奖品、多目标发布、区块链公证开奖",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(lambda c: c.data.startswith("join_"))
async def join_lottery(callback: types.CallbackQuery):
    lottery_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    # TODO: 校验是否关注指定频道 + 写入数据库
    await callback.answer("✅ 参与成功！祝你好运 🍀", show_alert=False)
    await callback.message.edit_reply_markup(reply_markup=None)
