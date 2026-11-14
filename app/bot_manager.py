"""
多 Bot 运行时管理器。
- 母号：使用 main.py 中的单一 bot 实例
- 子号：从数据库加载活跃的 clone bots，每个有独立 webhook 路径 /webhook/{bot_id}
"""
from typing import Dict
from aiogram import Bot, Dispatcher
from sqlalchemy import select

from app.database import async_session
from app.models import Bot as BotModel
from app.config import settings
from app.crypto_util import decrypt_token

_clones: Dict[int, tuple] = {}


async def load_clone_bots():
    async with async_session() as db:
        rows = (await db.execute(
            select(BotModel).where(
                BotModel.is_master == False,
                BotModel.is_active == True,
            )
        )).scalars().all()

    for row in rows:
        raw = row.bot_token or ""
        if not raw or raw.startswith("placeholder_"):
            continue
        token = decrypt_token(raw)
        try:
            await register_clone(row.id, token)
            print(f"✅ 子号已加载: id={row.id} @{row.bot_username}")
        except Exception as e:
            print(f"⚠️ 加载子号 {row.id} 失败: {e}")


async def register_clone(bot_id: int, token: str):
    if bot_id in _clones:
        return

    bot = Bot(token=token)
    dp = Dispatcher()

    from app.handlers import start, lottery, checkin
    from app.handlers.extra import router as extra_router
    dp.include_router(start.router)
    dp.include_router(lottery.router)
    dp.include_router(checkin.router)
    dp.include_router(extra_router)

    webhook_url = f"{settings.PUBLIC_HOST.rstrip('/')}/webhook/{bot_id}"
    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.safe_webhook_secret,
            drop_pending_updates=True,
        )
    except Exception as e:
        print(f"⚠️ 子号 {bot_id} webhook 设置失败: {e}")

    _clones[bot_id] = (bot, dp)


async def unregister_clone(bot_id: int):
    if bot_id in _clones:
        bot, _ = _clones.pop(bot_id)
        try:
            await bot.delete_webhook()
            await bot.session.close()
        except Exception:
            pass


def get_clone(bot_id: int):
    return _clones.get(bot_id)


def get_all_clones():
    return _clones


async def shutdown_all():
    for bot_id in list(_clones.keys()):
        await unregister_clone(bot_id)
