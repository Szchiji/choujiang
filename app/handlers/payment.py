from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from datetime import datetime, timedelta

from app.config import settings
from app.database import async_session
from app.models import CloneApplication, Bot

router = Router()

# 套餐定义（单位：XTR = Telegram Stars）
PLANS = {
    "monthly": {"title": "月付会员", "price": 500, "days": 30},
    "yearly": {"title": "年付会员", "price": 3500, "days": 365},
}


@router.message(Command("buy"))
async def buy_cmd(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="月付 · 500 Stars", callback_data="pay_monthly")],
            [InlineKeyboardButton(text="年付 · 3500 Stars", callback_data="pay_yearly")],
        ]
    )
    await message.answer(
        "💎 升级为付费克隆机器人，解锁全部功能：\n\n"
        "✅ 无限次抽奖\n"
        "✅ 多奖品配置\n"
        "✅ 多目标发布\n"
        "✅ 强制多频道关注\n"
        "✅ 数据导出\n\n"
        "请选择套餐：",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("pay_"))
async def process_plan(callback: types.CallbackQuery):
    plan = callback.data.replace("pay_", "")
    info = PLANS.get(plan)
    if not info:
        await callback.answer("❌ 套餐不存在", show_alert=True)
        return

    # 发送发票（Telegram Stars）
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=info["title"],
        description=f"LuckyDraw Cloud {info['title']}，有效期 {info['days']} 天",
        payload=f"clone_{plan}_{callback.from_user.id}",
        provider_token="",               # Stars 支付留空
        currency="XTR",                  # XTR = Telegram Stars
        prices=[LabeledPrice(label=info["title"], amount=info["price"])],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    """预校验：确认订单可以支付"""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    """支付成功后处理"""
    payload = message.successful_payment.invoice_payload
    # payload 格式：clone_{plan}_{user_id}
    parts = payload.split("_")
    if len(parts) != 3 or parts[0] != "clone":
        return

    plan = parts[1]
    user_id = int(parts[2])
    info = PLANS.get(plan)
    if not info:
        return

    # 创建克隆申请工单（状态：已支付，待管理员创建 Bot）
    async with async_session() as db:
        application = CloneApplication(
            user_id=user_id,
            plan=plan,
            status="paid",
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)

    # 通知用户
    await message.answer(
        f"✅ 支付成功！\n\n"
        f"📦 套餐：{info['title']}\n"
        f"💰 金额：{message.successful_payment.total_amount} Stars\n"
        f"🆔 订单号：{application.id}\n\n"
        f"请等待管理员创建您的专属机器人，通常 5 分钟内完成。"
    )

    # 通知所有管理员
    for admin_id in settings.admin_ids_list:
        try:
            await message.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔔 <b>新订单</b>\n\n"
                    f"👤 用户：<a href='tg://user?id={user_id}'>用户{user_id}</a>\n"
                    f"📦 套餐：{info['title']}\n"
                    f"🆔 订单号：{application.id}\n\n"
                    f"请创建子机器人后回复用户。"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"通知管理员 {admin_id} 失败: {e}")
