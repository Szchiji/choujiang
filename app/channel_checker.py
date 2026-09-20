from typing import List
from aiogram import Bot
from aiogram.types import ChatMember


async def check_channels(bot: Bot, user_id: int, channels: List[str]) -> dict:
    """校验用户是否关注了所有指定频道"""
    if not channels:
        return {"ok": True, "failed": []}

    failed = []
    for ch in channels:
        try:
            chat_id = ch
            if not ch.startswith("-") and not ch.startswith("@"):
                chat_id = f"@{ch}"

            member: ChatMember = await bot.get_chat_member(
                chat_id=chat_id,
                user_id=user_id,
            )
            if member.status in ("left", "kicked"):
                failed.append(ch)
        except Exception as e:
            print(f"校验频道 {ch} 失败: {e}")
            failed.append(ch)

    return {"ok": len(failed) == 0, "failed": failed}


async def check_channels_for_draw(bot: Bot, user_id: int, channels: List[str]) -> bool:
    result = await check_channels(bot, user_id, channels)
    return result["ok"]


def build_channel_links(channels: List[str]) -> str:
    lines = []
    for ch in channels:
        if ch.startswith("@"):
            lines.append(f"👉 https://t.me/{ch.lstrip('@')}")
        elif ch.startswith("-100"):
            lines.append(f"👉 https://t.me/c/{ch.replace('-100', '')}")
        else:
            lines.append(f"👉 {ch}")
    return "\n".join(lines)
