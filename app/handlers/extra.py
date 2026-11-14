"""模板、排行榜、核销、看板相关命令"""
from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select, desc
from urllib.parse import urlencode

from app.config import settings
from app.database import async_session
from app.models import LotteryTemplate, UserMeta, PrizeClaim, Lottery

router = Router()


@router.message(Command("templates"))
async def list_templates(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as db:
        rows = (await db.execute(
            select(LotteryTemplate)
            .where(LotteryTemplate.owner_id == user_id)
            .order_by(desc(LotteryTemplate.created_at))
            .limit(10)
        )).scalars().all()

    if not rows:
        await message.answer("📭 暂无模板。\n创建抽奖后使用 /savetpl <名称> 保存当前配置。")
        return

    text = "<b>📋 我的抽奖模板</b>\n\n"
    for t in rows:
        text += f"• <b>{t.name}</b> (ID: <code>{t.id}</code>)\n"
    text += "\n使用 /usetpl <ID> 加载模板"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("savetpl"))
async def save_template(message: types.Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("用法：/savetpl <模板名称>")
        return

    name = args[1].strip()
    user_id = message.from_user.id

    # 取用户最近一次抽奖作为模板
    async with async_session() as db:
        last = (await db.execute(
            select(Lottery)
            .where(Lottery.bot_id == user_id)
            .order_by(desc(Lottery.created_at))
            .limit(1)
        )).scalar_one_or_none()

        if not last:
            await message.answer("❌ 你还没有创建过抽奖，无法保存模板")
            return

        config = {
            "title": last.title,
            "subtitle": last.subtitle,
            "prizes": last.prizes,
            "targets": last.targets,
            "channels": last.channels,
            "draw_mode": last.draw_mode,
            "target_count": last.target_count,
        }
        db.add(LotteryTemplate(owner_id=user_id, name=name, config=config))
        await db.commit()

    await message.answer(f"✅ 模板「{name}」已保存")


@router.message(Command("usetpl"))
async def use_template(message: types.Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("用法：/usetpl <模板ID>")
        return

    tpl_id = int(args[1])
    user_id = message.from_user.id

    async with async_session() as db:
        tpl = (await db.execute(
            select(LotteryTemplate).where(
                LotteryTemplate.id == tpl_id,
                LotteryTemplate.owner_id == user_id,
            )
        )).scalar_one_or_none()

    if not tpl:
        await message.answer("❌ 模板不存在")
        return

    params = urlencode({"uid": user_id, "tpl": tpl_id})
    url = f"{settings.PUBLIC_HOST}/create?{params}"
    await message.answer(
        f"📋 模板「{tpl.name}」已准备\n\n"
        f'🔗 <a href="{url}">点击打开创建页（已预填）</a>',
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("dashboard"))
async def dashboard_cmd(message: types.Message):
    user_id = message.from_user.id
    params = urlencode({"uid": user_id})
    url = f"{settings.PUBLIC_HOST}/dashboard?{params}"
    await message.answer(
        f"📊 <b>我的数据看板</b>\n\n"
        f'🔗 <a href="{url}">打开看板</a>',
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("leaderboard"))
async def leaderboard(message: types.Message):
    async with async_session() as db:
        rows = (await db.execute(
            select(UserMeta)
            .where(UserMeta.referral_count > 0)
            .order_by(desc(UserMeta.referral_count))
            .limit(10)
        )).scalars().all()

    if not rows:
        await message.answer("📊 暂无邀请排行数据")
        return

    text = "<b>🏆 邀请排行榜</b>\n\n"
    for i, u in enumerate(rows, 1):
        text += f"{i}. <code>{u.user_id}</code> — {u.referral_count} 人\n"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("claim"))
async def claim_prize(message: types.Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("用法：/claim <核销码>")
        return

    code = args[1].strip().upper()
    async with async_session() as db:
        claim = (await db.execute(
            select(PrizeClaim).where(PrizeClaim.claim_code == code)
        )).scalar_one_or_none()

        if not claim:
            await message.answer("❌ 核销码不存在")
            return

        if claim.claimed:
            await message.answer("✅ 该奖品已核销")
            return

        from datetime import datetime
        claim.claimed = True
        claim.claimed_at = datetime.now()
        await db.commit()

    await message.answer(
        f"🎉 <b>核销成功！</b>\n\n"
        f"奖品：{claim.prize_name}\n"
        f"活动 ID：LK-{claim.lottery_id}",
        parse_mode="HTML",
    )
