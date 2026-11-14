from datetime import datetime, timedelta
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
from app.bot_instance import get_bot
from app.message_builder import build_lottery_message

app = FastAPI(title="LuckyDraw Web")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==================== 页面路由 ====================

@app.get("/create", response_class=HTMLResponse)
async def create_page(uid: int = 0):
    """创建抽奖页面"""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{UID}}", str(uid))
    return HTMLResponse(content=html)


@app.get("/verify", response_class=HTMLResponse)
async def verify_page(block: int = 0, hash: str = "", lottery: int = 0):
    """区块链验证页面"""
    html = (STATIC_DIR / "verify.html").read_text(encoding="utf-8")
    html = html.replace("{{BLOCK_HEIGHT}}", str(block))
    html = html.replace("{{BLOCK_HASH}}", hash)
    html = html.replace("{{LOTTERY_ID}}", str(lottery))
    return HTMLResponse(content=html)


@app.get("/plaza", response_class=HTMLResponse)
async def plaza_page():
    """LuckyDraw 广场"""
    html = (STATIC_DIR / "plaza.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """管理后台（自动注入 admin token）"""
    html = (STATIC_DIR / "admin.html").read_text(encoding="utf-8")
    html = html.replace("{{ADMIN_TOKEN}}", settings.safe_webhook_secret)
    return HTMLResponse(content=html)


# ==================== 配额与辅助函数 ====================

async def check_and_deduct_quota(user_id: int) -> tuple[bool, str]:
    """检查并扣减配额。优先使用 free_quota，然后 extra_credits。"""
    async with async_session() as db:
        meta = (await db.execute(
            select(UserMeta).where(UserMeta.user_id == user_id)
        )).scalar_one_or_none()

        if not meta:
            meta = UserMeta(
                user_id=user_id,
                free_quota=1,
                extra_credits=0,
                trial_start=datetime.now(),
                trial_end=datetime.now() + timedelta(days=3),
            )
            db.add(meta)
            await db.commit()
            await db.refresh(meta)

        # 首次使用自动开通试用
        if not meta.trial_start:
            meta.trial_start = datetime.now()
            meta.trial_end = datetime.now() + timedelta(days=3)

        if (meta.free_quota or 0) > 0:
            meta.free_quota -= 1
            await db.commit()
            return True, "free"

        if (meta.extra_credits or 0) > 0:
            meta.extra_credits -= 1
            await db.commit()
            return True, "extra"

        await db.commit()
        return False, "配额不足，请签到、邀请好友或升级套餐"


def normalize_chat_id(raw: str) -> str | int:
    """把 t.me 链接、@username、-100xxx 统一成 Telegram 可接受的 chat_id"""
    s = (raw or "").strip()
    if not s:
        return s
    if s.startswith("https://t.me/"):
        username = s.split("https://t.me/")[-1].split("/")[0].lstrip("@")
        return f"@{username}" if username else s
    if s.startswith("http://t.me/"):
        username = s.split("http://t.me/")[-1].split("/")[0].lstrip("@")
        return f"@{username}" if username else s
    if s.startswith("@") or s.startswith("-"):
        return s
    if s.lstrip("-").isdigit():
        return int(s)
    return f"@{s}"


# ==================== 业务 API ====================

@app.post("/api/lottery")
async def create_lottery_api(request: Request):
    """创建抽奖（Web 后台表单提交）"""
    data = await request.json()
    uid = int(data.get("uid") or 0)

    if not uid:
        return JSONResponse({"ok": False, "message": "缺少用户身份"}, status_code=400)

    if not data.get("title"):
        return JSONResponse({"ok": False, "message": "标题不能为空"}, status_code=400)

    prizes = data.get("prizes") or []
    if not prizes or not any(p.get("name") for p in prizes):
        return JSONResponse({"ok": False, "message": "至少需要一个有效奖品"}, status_code=400)

    targets = data.get("targets") or []
    if not targets:
        return JSONResponse({"ok": False, "message": "至少需要一个发布目标"}, status_code=400)

    # 配额检查
    ok, reason = await check_and_deduct_quota(uid)
    if not ok:
        return JSONResponse({"ok": False, "message": reason}, status_code=403)

    # 解析开奖时间
    draw_time = None
    if data.get("draw_mode") == "time" and data.get("draw_time"):
        try:
            draw_time = datetime.fromisoformat(data["draw_time"].replace("Z", ""))
        except Exception:
            pass

    # 入库
    async with async_session() as db:
        lottery = Lottery(
            bot_id=uid,  # 母号阶段用创建者 user_id 代替，便于 /my 查询
            title=data["title"],
            subtitle=data.get("subtitle"),
            cover_image=data.get("cover_image"),
            prizes=prizes,
            targets=targets,
            channels=data.get("channels") or [],
            draw_mode=data.get("draw_mode") or "time",
            draw_time=draw_time,
            target_count=data.get("target_count"),
            status="ongoing",
            is_public=True,
        )
        db.add(lottery)
        await db.commit()
        await db.refresh(lottery)
        lottery_id = lottery.id

    # 发布到目标群组/频道
    bot = get_bot()
    sent = 0
    failed = []
    if bot:
        total_prizes = sum(p.get("count", 0) for p in prizes)
        probability = (total_prizes / max(data.get("target_count") or 100, 1)) * 100
        countdown = "等待开奖"
        if draw_time:
            delta = draw_time - datetime.now()
            if delta.total_seconds() > 0:
                d = delta.days
                h = delta.seconds // 3600
                m = (delta.seconds % 3600) // 60
                countdown = f"{d}天{h}时{m}分"

        text, keyboard = build_lottery_message(
            lottery_id=lottery_id,
            title=data["title"],
            subtitle=data.get("subtitle") or "",
            prizes=prizes,
            cover_image=data.get("cover_image"),
            participants=0,
            countdown=countdown,
            probability=min(probability, 100.0),
            verify_url=f"{settings.PUBLIC_HOST}/verify?lottery={lottery_id}",
        )

        for raw_target in targets:
            try:
                chat_id = normalize_chat_id(raw_target)
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
                sent += 1
            except Exception as e:
                failed.append(f"{raw_target}: {e}")

    msg = f"抽奖创建成功，已发布到 {sent} 个目标"
    if failed:
        msg += f"，{len(failed)} 个失败"

    return JSONResponse({
        "ok": True,
        "message": msg,
        "lottery_id": lottery_id,
        "sent": sent,
        "failed": failed,
    })


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
        participants = (await db.execute(
            select(func.count(Participant.id))
        )).scalar() or 0

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
    if not token or token != settings.safe_webhook_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/api/admin/stats")
async def admin_stats(x_admin_token: str = Header(None)):
    _check_admin(x_admin_token)
    async with async_session() as db:
        users = (await db.execute(
            select(func.count(UserMeta.user_id))
        )).scalar() or 0

        lotteries = (await db.execute(
            select(func.count(Lottery.id))
        )).scalar() or 0

        bots = (await db.execute(
            select(func.count(Bot.id)).where(
                Bot.is_master == False,
                Bot.is_active == True,
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
                "created_at": (
                    u.created_at.strftime("%Y-%m-%d")
                    if u.created_at else ""
                ),
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
                "created_at": (
                    o.created_at.strftime("%Y-%m-%d %H:%M")
                    if o.created_at else ""
                ),
            }
            for o in rows
        ]


@app.post("/api/admin/orders/{order_id}/approve")
async def admin_approve(order_id: int, x_admin_token: str = Header(None)):
    """批准订单：更新状态并创建对应的 Bot 记录（占位，实际多 Bot 运行仍需后续完善）"""
    _check_admin(x_admin_token)
    async with async_session() as db:
        app_row = (await db.execute(
            select(CloneApplication).where(CloneApplication.id == order_id)
        )).scalar_one_or_none()

        if not app_row:
            raise HTTPException(status_code=404, detail="订单不存在")

        app_row.status = "approved"
        app_row.processed_at = datetime.now()

        # 创建 Bot 记录（如果还没有）
        existing = (await db.execute(
            select(Bot).where(Bot.owner_id == app_row.user_id, Bot.is_master == False)
        )).scalar_one_or_none()

        if not existing:
            days = {"monthly": 30, "yearly": 365, "lifetime": 36500}.get(app_row.plan, 30)
            db.add(Bot(
                owner_id=app_row.user_id,
                bot_token=app_row.bot_token or f"placeholder_{app_row.user_id}",
                bot_username=app_row.bot_name or f"clone_{app_row.user_id}",
                is_master=False,
                is_active=True,
                expire_time=datetime.now() + timedelta(days=days),
            ))

        await db.commit()

    return {"ok": True, "message": "已批准并创建子号记录"}


@app.get("/api/admin/bots")
async def admin_bots(x_admin_token: str = Header(None)):
    _check_admin(x_admin_token)
    async with async_session() as db:
        rows = (await db.execute(
            select(Bot).order_by(desc(Bot.created_at)).limit(200)
        )).scalars().all()

        return [
            {
                "id": b.id,
                "owner_id": b.owner_id,
                "bot_username": b.bot_username,
                "is_master": b.is_master,
                "is_active": b.is_active,
                "expire_time": (
                    b.expire_time.strftime("%Y-%m-%d")
                    if b.expire_time else None
                ),
            }
            for b in rows
        ]
