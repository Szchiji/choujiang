from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_lottery_message(
    lottery_id: int,
    title: str,
    subtitle: str,
    prizes: list,
    cover_image: str = None,
    participants: int = 0,
    countdown: str = "等待开奖",
    probability: float = 0.0,
    verify_url: str = None,
):
    """构建 Telegram 抽奖卡片消息（HTML 格式）"""
    text = ""

    if cover_image:
        text += f'<a href="{cover_image}">&#8205;</a>\n\n'

    text += "✦ <b>LuckyDraw Cloud</b>\n\n"
    text += f"<b>✨ {title}</b>\n"
    if subtitle:
        text += f"🎯 {subtitle}\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "<b>🏆 奖品清单</b>\n"
    for prize in prizes:
        icon = prize.get("icon", "🎁")
        text += f"{icon} {prize['name']}  ─  ×{prize['count']}\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"⏳ 倒计时：<code>{countdown}</code>\n"
    text += f"👥 已参与：<b>{participants}</b> 人\n"
    text += f"📊 中奖率：<b>{probability:.2f}%</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "<i>⛓️ 区块链公证 · 公开透明</i>\n"
    text += f"🆔 <code>LK-{lottery_id}</code>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔥 立即参与抽奖",
                    callback_data=f"join_{lottery_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 验证公平性",
                    url=verify_url or "https://example.com",
                )
            ],
        ]
    )
    return text, keyboard
