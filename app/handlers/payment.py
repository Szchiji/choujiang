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
from app.models import CloneApplication

router = Router()

# 套餐定义（单位：XTR = Telegram Stars）
PLANS = {
    "monthly": {"title": "月付会员", "price": 500, "days": 30},
    "yearly": {"title": "年付会员", "price": 3500, "days": 365},
    "lifetime": {"title": "终身会员", "price": 10000, "days": 36500},
}


@router.message(Command("buy"))
async def buy_cmd(message: types.Message):
    """展示套餐选项"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="月付 · 500 Stars", callback_data="pay_monthly")],
            [InlineKeyboardButton(text="年付 · 3500 Stars", callback_data="pay_yearly")],
            [InlineKeyboardButton(text="终身 · 10000 Stars", callback_data="pay_lifetime")],
        ]
    )
    await message.answer(
        "💎 <b>升级为付费克隆机器人</b>\n\n"
        "解锁全部功能：\n"
        "✅ 无限次抽奖\n"
        "✅ 多奖品配置（名称+数量）\n"
        "✅ 多目标发布（同时发到 N 个群/频道）\n"
        "✅ 强制多频道关注\n"
        "✅ 数据导出 Excel\n"
        "✅ 隐私模式（不上广场）\n"
        "✅ 自定义机器人名称/头像\n\n"
        "请选择套餐：",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("pay_"))
async def process_plan(callback: types.CallbackQuery):
    """处理套餐选择，发送支付发票"""
    plan = callback.data.replace("pay_", "")
    info = PLANS.get(plan)
    if not info:
        await callback.answer("❌ 套餐不存在", show_alert=True)
        return

    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=info["title"],
            description=f"LuckyDraw Cloud {info['title']}，有效期 {info['days']} 天，全部功能解锁",
            payload=f"clone_{plan}_{callback.from_user.id}",
            provider_token="",           # Telegram Stars 支付留空
            currency="XTR",              # XTR = Telegram Stars
            prices=[LabeledPrice(label=info["title"], amount=info["price"])],
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ 创建支付失败：{e}", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    """预校验：确认订单可以支付"""
    # 这里可以校验用户是否已经购买过、是否有资格购买等
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    """支付成功后处理"""
    payment = message.successful_payment
    payload = payment.invoice_payload

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
        application_id = application.id

    # 通知用户
    await message.answer(
        f"✅ <b>支付成功！</b>\n\n"
        f"📦 套餐：<b>{info['title']}</b>\n"
        f"💰 金额：<b>{payment.total_amount} Stars</b>\n"
        f"🆔 订单号：<code>#{application_id}</code>\n\n"
        f"⏳ 管理员将在 5 分钟内为您创建专属机器人。\n"
        f"创建完成后会私聊通知您，请耐心等待！",
        parse_mode="HTML",
    )

    # 通知所有管理员
    for admin_id in settings.admin_ids_list:
        try:
            await message.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔔 <b>新订单待处理</b>\n\n"
                    f"👤 用户：<a href='tg://user?id={user_id}'>用户 {user_id}</a>\n"
                    f"📦 套餐：<b>{info['title']}</b>\n"
                    f"💰 金额：{payment.total_amount} Stars\n"
                    f"🆔 订单号：<code>#{application_id}</code>\n\n"
                    f"👉 请创建子机器人后联系用户。"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"通知管理员 {admin_id} 失败: {e}")


@router.message(Command("orders"))
async def my_orders(message: types.Message):
    """查看我的订单"""
    user_id = message.from_user.id

    async with async_session() as db:
        from sqlalchemy import select, desc
        rows = (await db.execute(
            select(CloneApplication)
            .where(CloneApplication.user_id == user_id)
            .order_by(desc(CloneApplication.created_at))
            .limit(10)
        )).scalars().all()

    if not rows:
        await message.answer("📭 你还没有订单记录。\n发送 /buy 查看套餐。")
        return

    status_map = {
        "paid": "🟡 待处理",
        "approved": "🟢 已激活",
        "rejected": "🔴 已拒绝",
        "pending": "⚪ 待支付",
    }

    text = "📋 <b>我的订单</b>\n\n"
    for o in rows:
        info = PLANS.get(o.plan, {})
        text += f"🆔 <code>#{o.id}</code>\n"
        text += f"   📦 {info.get('title', o.plan)}\n"
        text += f"   📅 {o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else ''}\n"
        text += f"   状态：{status_map.get(o.status, o.status)}\n\n"

    await message.answer(text, parse_mode="HTML")
