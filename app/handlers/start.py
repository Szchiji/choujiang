from aiogram import Router, types
from aiogram.filters import Command, CommandObject

from app.handlers.checkin import process_referral

router = Router()


@router.message(Command("start"))
async def start_cmd(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    payload = command.args or ""

    # 处理邀请链接：/start ref_123456
    if payload.startswith("ref_"):
        try:
            inviter_id = int(payload.replace("ref_", ""))
            await process_referral(message.bot, inviter_id, user_id)
        except (ValueError, Exception) as e:
            print(f"处理邀请失败: {e}")

    await message.answer(
        "🎯 欢迎使用 <b>LuckyDraw Cloud</b>！\n\n"
        "免费版每日可创建 1 次抽奖。\n"
        "发送 /create 开始创建你的抽奖活动。\n\n"
        "📖 <b>常用命令</b>\n"
        "/create - 创建抽奖\n"
        "/checkin - 每日签到\n"
        "/invite - 邀请好友\n"
        "/my - 我的抽奖\n"
        "/help - 帮助",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "<b>📖 命令列表</b>\n\n"
        "/start - 欢迎信息\n"
        "/create - 创建抽奖（返回 Web 链接）\n"
        "/checkin - 每日签到领次数\n"
        "/invite - 邀请好友得奖励\n"
        "/my - 查看我创建的抽奖\n"
        "/clone - 申请克隆专属机器人\n"
        "/buy - 购买付费套餐",
        parse_mode="HTML",
    )
