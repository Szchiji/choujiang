from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.config import settings
from app.database import init_db, close_db
from app.handlers import start, lottery, admin, payment, checkin
from app.handlers.extra import router as extra_router
from app.scheduler import start_scheduler
from app.bot_instance import set_bot
from app.bot_manager import load_clone_bots, get_clone, shutdown_all

bot = Bot(token=settings.BOT_TOKEN)
set_bot(bot)

dp = Dispatcher()
dp.include_router(start.router)
dp.include_router(lottery.router)
dp.include_router(admin.router)
dp.include_router(payment.router)
dp.include_router(checkin.router)
dp.include_router(extra_router)

SAFE_SECRET = settings.safe_webhook_secret


async def set_menu_button():
    """启动时自动设置 Menu Button 为 Mini App"""
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🎯 抽奖",
                web_app=WebAppInfo(url=f"{settings.PUBLIC_HOST.rstrip('/')}/app"),
            )
        )
        print(f"✅ Menu Button 已设置：{settings.PUBLIC_HOST}/app")
    except Exception as e:
        print(f"⚠️ Menu Button 设置失败：{e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    try:
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            secret_token=SAFE_SECRET,
            drop_pending_updates=True,
        )
        print(f"✅ 母号 Webhook 已设置：{settings.WEBHOOK_URL}")
    except Exception as e:
        print(f"⚠️ 母号 Webhook 设置失败：{e}")

    await set_menu_button()
    await load_clone_bots()
    start_scheduler(bot)
    print("✅ LuckyDraw Cloud 启动完成")

    yield

    print("⏹️ 正在关闭服务...")
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    await shutdown_all()
    await close_db()


app = FastAPI(title="LuckyDraw Cloud", lifespan=lifespan)


@app.post("/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != SAFE_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    update = types.Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.post("/webhook/{bot_id}")
async def clone_webhook(bot_id: int, request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != SAFE_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    clone = get_clone(bot_id)
    if not clone:
        raise HTTPException(status_code=404, detail="Bot not found")

    clone_bot, clone_dp = clone
    update = types.Update.model_validate(await request.json())
    await clone_dp.feed_update(clone_bot, update)
    return {"ok": True}


@app.get("/health")
async def health():
    status = {"status": "ok", "db": False, "redis": False}
    try:
        from app.database import async_session
        from sqlalchemy import text
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        status["db"] = True
    except Exception:
        pass

    try:
        from app.redis_client import redis
        await redis.ping()
        status["redis"] = True
    except Exception:
        pass

    if not status["db"] or not status["redis"]:
        status["status"] = "degraded"
    return status


from app.web.app import app as web_app
app.mount("/", web_app)
