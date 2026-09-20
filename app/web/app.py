from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, desc, update

from app.config import settings
from app.database import async_session
from app.models import (
    Lottery, Participant, UserMeta, CloneApplication, Bot,
)

app = FastAPI(title="LuckyDraw Web")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==================== 页面路由 ====================

@app.get("/create", response_class=HTMLResponse)
async def create_page(uid: int = 0):
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{UID}}", str(uid))
    return HTMLResponse(content=html)


@app.get("/verify", response_class=HTMLResponse)
async def verify_page(block: int = 0, hash: str = "", lottery: int = 0):
    html = (STATIC_DIR / "verify.html").read_text(encoding="utf-8")
    html = html.replace("{{BLOCK_HEIGHT}}", str(block))
    html = html.replace("{{BLOCK_HASH}}", hash)
    html = html.replace("{{LOTTERY_ID}}", str(lottery))
    return HTMLResponse(content=html)


@app.get("/plaza", response_class=HTMLResponse)
async def plaza_page():
    html = (STATIC_DIR / "plaza.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    html = (STATIC_DIR / "admin.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


# ==================== 业务 API ====================

@app.post("/api/lottery")
async def create_lottery_api(request: Request):
    """创建抽奖（Web 后台表单提交）"""
    data = await request.json()
    # TODO: 校验用户配额 + 存入数据库 + 调用 Bot 发送消息
    return JSONResponse({"ok": True, "message": "抽奖创建成功"})


@app.get("/api/plaza")
async def api_plaza(q: str = ""):
    """LuckyDraw 广场：返回公开进行中的抽奖"""
    async with async_session() as db:
        stmt = (
            select(Lottery)
            .where(Lottery.is_public == True, Lottery.status == "ongoing")
            .order_by(desc(Lottery.created_at))
            .limit(100)
        )
        if q:
            stmt = stmt.where(Lottery.title.ilike(f"%{q}%"))

        result = await db.execute(stmt)
        lotteries = list(result.scalars().all())

        items = []
        for lot in lotteries:
            count_stmt = select(func.count(Participant.id)).where(
                Participant.lottery_id == lot.id
            )
            count = (await db.execute(count_stmt)).scalar() or 0

            countdown = "待定"
            if lot.draw_time:
                delta = lot.draw_time - datetime.now()
                if delta.total_seconds() > 0:
                    d = delta.days
                    h = delta.seconds // 3600
                    m = (delta.seconds % 3600) // 60
                    countdown = f"{d}天{h}时{m}分"
                else:
                    countdown = "即将开奖"

            items.append({
                "id": lot.id,
                "title": lot.title,
                "subtitle": lot.subtitle or "",
                "cover_image": lot.cover_image,
                "prizes": lot.prizes or [],
                "participants": count,
                "countdown": countdown,
                "bot_link": f"https://t.me/your_bot?start=lottery_{lot.id}",
            })

        total = (await db.execute(select(func.count(Lottery.id)))).scalar() or 0
        ongoing = (await db.execute(
            select(func.count(Lottery.id)).where(Lottery.status == "ongoing")
        )).scalar() or 0
        participants = (await db.execute(select(func.count(Participant.id)))).scalar() or 0

        return {
            "lotteries": items,
            "stats": {
                "total": total,
                "ongoing": ongoing,
                "participants": participants,
                "today": 0,
            },
        }


# ==================== 管理后台 API ====================

def _check_admin(token: str):
    if token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/api/admin/stats")
async def admin_stats(x_admin_token: str = Header(None)):
    _check_admin(x_admin_token)
    async with async_session() as db:
        users = (await db.execute(select(func.count(UserMeta.user_id)))).scalar() or 0
        lotteries = (await db.execute(select(func.count(Lottery.id)))).scalar() or 0
        bots = (await db.execute(
            select(func.count(Bot.id)).where(
                Bot.is_master == False, Bot.is_active == True
            )
        )).scalar() or 0
        orders = (await db.execute(
            select(func.count(CloneApplication.id)).where(
                CloneApplication.status.in_(["paid", "approved"])
            )
        )).scalar() or 0
        return {
            "users": users,
            "lotteries": lotteries,
            "bots": bots,
            "revenue": orders * 500,
        }


@app.get("/api/admin/users")
async def admin_users(x_admin_token: str = Header(None)):
    _check_admin(x_admin_token)
    async with async_session() as db:
        rows = (await db.execute(
            select(UserMeta).order_by(desc(UserMeta.created_at)).limit(200)
        )).scalars().all()
        return [
            {
                "user_id": u.user_id,
                "sign_in_streak": u.sign_in_streak or 0,
                "extra_credits": u.extra_credits or 0,
                "referral_count": u.referral_count or 0,
                "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
            }
            for u in rows
        ]


@app.get("/api/admin/orders")
async def admin_orders(x_admin_token: str = Header(None)):
    _check_admin(x_admin_token)
    async with async_session() as db:
        rows = (await db.execute(
            select(CloneApplication)
            .order_by(desc(CloneApplication.created_at))
            .limit(200)
        )).scalars().all()
        return [
            {
                "id": o.id,
                "user_id": o.user_id,
                "plan": o.plan,
                "status": o.status,
                "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "",
            }
            for o in rows
        ]


@app.post("/api/admin/orders/{order_id}/approve")
async def admin_approve(order_id: int, x_admin_token: str = Header(None)):
    _check_admin(x_admin_token)
    async with async_session() as db:
        await db.execute(
            update(CloneApplication)
            .where(CloneApplication.id == order_id)
            .values(status="approved", processed_at=datetime.now())
        )
        await db.commit()
    return {"ok": True}


@app.get("/api/admin/bots")
async def admin_bots(x_admin_token: str = Header(None)):
    _check_admin(x_admin_token)
    async with async_session() as db:
        rows = (await db.execute(select(Bot).limit(200))).scalars().all()
        return [
            {
                "id": b.id,
                "owner_id": b.owner_id,
                "bot_username": b.bot_username,
                "is_master": b.is_master,
                "is_active": b.is_active,
                "expire_time": b.expire_time.strftime("%Y-%m-%d") if b.expire_time else None,
            }
            for b in rows
        ]
