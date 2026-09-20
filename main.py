import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types

from app.config import settings
from app.database import init_db
from app.handlers import start, lottery, admin

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start.router)
dp.include_router(lottery.router)
dp.include_router(admin.router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await bot.set_webhook(
        url=settings.WEBHOOK_URL,
        secret_token=settings.WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    yield
    await bot.delete_webhook()


app = FastAPI(title="LuckyDraw Cloud", lifespan=lifespan)


@app.post("/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    update = types.Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
