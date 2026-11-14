from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from datetime import datetime
from sqlalchemy import select, desc

from app.config import settings
from app.database import async_session
from app.models import CloneApplication, Bot

router = Router()

PLANS = {
    "monthly": {"title": "月付会员", "price": 500, "days": 30},
    "yearly": {"title": "年付会员", "price": 3500, "days": 365},
    "lifetime": {"title": "终身会员", "price": 10000, "days": 36500},
}

# 临时存储等待提交 token 的用户
_waiting_token: dict[int, int] = {}  # user_id -> application_id


@router.message(Command("buy"))
async def buy_cmd(message: types.Message):
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
        "✅ 多奖品配置\n"
        "✅ 多目标发布\n"
        "✅ 强制多频道关注\n"
        "✅ 数据导出\n"
        "✅ 隐私模式\n"
        "✅ 自定义品牌\n\n"
        "请选择套餐：",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("pay_"))
async def process_plan(callback: types.CallbackQuery):
    plan = callback.data.replace("pay_", "")
    info = PLANS.get(plan)
    if not info:
        await callback.answer("❌ 套餐不存在", show_alert=True)
        return

    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=info["title"],
            description=f"LuckyDraw Cloud {info['title']}，有效期 {info['days']} 天",
            payload=f"clone_{plan}_{callback.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=info["title"], amount=info["price"])],
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ 创建支付失败：{e}", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload

    parts = payload.split("_")
    if len(parts) != 3 or parts[0] != "clone":
        return

    plan = parts[1]
    user_id = int(parts[2])
    info = PLANS.get(plan)
    if not info:
        return

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

    _waiting_token[user_id] = application_id

    await message.answer(
        f"✅ <b>支付成功！</b>\n\n"
        f"📦 套餐：<b>{info['title']}</b>\n"
        f"💰 金额：<b>{payment.total_amount} Stars</b>\n"
        f"🆔 订单号：<code>#{application_id}</code>\n\n"
        f"🤖 请发送你的 <b>Bot Token</b>（从 @BotFather 获取）\n"
        f"格式：<code>123456:ABC-DEF...</code>\n\n"
        f"发送后管理员将为你开通专属机器人。",
        parse_mode="HTML",
    )

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
                    f"等待用户提交 Bot Token。"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"通知管理员 {admin_id} 失败: {e}")


@router.message(lambda m: m.from_user and m.from_user.id in _waiting_token and m.text and ":" in m.text)
async def receive_token(message: types.Message):
    user_id = message.from_user.id
    app_id = _waiting_token.pop(user_id, None)
    if not app_id:
        return

    token = message.text.strip()
    if len(token) < 20 or ":" not in token:
        _waiting_token[user_id] = app_id
        await message.answer("❌ Token 格式不正确，请重新发送")
        return

    async with async_session() as db:
        app_row = (await db.execute(
            select(CloneApplication).where(CloneApplication.id == app_id)
        )).scalar_one_or_none()
        if app_row:
            app_row.bot_token = token
            await db.commit()

    await message.answer(
        "✅ <b>Token 已收到！</b>\n\n"
        "管理员将尽快为你开通。开通后你会收到通知。\n\n"
        "💡 开通后可使用 /setwelcome 设置自定义欢迎语",
        parse_mode="HTML",
    )

    for admin_id in settings.admin_ids_list:
        try:
            await message.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔑 <b>用户已提交 Token</b>\n\n"
                    f"订单：<code>#{app_id}</code>\n"
                    f"用户：<code>{user_id}</code>\n"
                    f"使用 /approve {app_id} 批准"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.message(Command("setwelcome"))
async def set_welcome(message: types.Message):
    """设置白标欢迎语（仅子号拥有者）"""
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("用法：/setwelcome <欢迎语 HTML>")
        return

    welcome = args[1]
    user_id = message.from_user.id

    async with async_session() as db:
        bot_row = (await db.execute(
            select(Bot).where(Bot.owner_id == user_id, Bot.is_master == False, Bot.is_active == True)
        )).scalar_one_or_none()

        if not bot_row:
            await message.answer("❌ 你还没有激活的子号")
            return

        bot_row.custom_welcome = welcome
        await db.commit()

    await message.answer("✅ 欢迎语已更新")


@router.message(Command("orders"))
async def my_orders(message: types.Message):
    user_id = message.from_user.id

    async with async_session() as db:
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
