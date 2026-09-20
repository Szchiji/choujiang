from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types

from app.config import settings
from app.database import init_db, close_db
from app.handlers import start, lottery, admin, payment, checkin
from app.scheduler import start_scheduler

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start.router)
dp.include_router(lottery.router)
dp.include_router(admin.router)
dp.include_router(payment.router)
dp.include_router(checkin.router)

# 使用清理后的 secret
SAFE_SECRET = settings.safe_webhook_secret


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    await init_db()

    try:
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            secret_token=SAFE_SECRET,
            drop_pending_updates=True,
        )
        print(f"✅ Webhook 已设置：{settings.WEBHOOK_URL}")
        print(f"✅ Secret 长度：{len(SAFE_SECRET)}")
    except Exception as e:
        print(f"⚠️ Webhook 设置失败：{e}")

    start_scheduler(bot)
    print("✅ LuckyDraw Cloud 启动完成")

    yield

    # 关闭
    print("⏹️ 正在关闭服务...")
    try:
        await bot.delete_webhook()
    except Exception:
        pass
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


@app.get("/health")
async def health():
    return {"status": "ok"}


# ==================== 挂载 Web 页面 ====================
from app.web.app import app as web_app
app.mount("/", web_app)
