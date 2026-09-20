from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta

from app.redis_client import redis, redis_lock
from app.lottery_service import get_due_lotteries, execute_draw
from app.database import async_session
from app.models import Bot
from sqlalchemy import select, update

scheduler = AsyncIOScheduler()


async def job_auto_draw(bot):
    """每分钟检查自动开奖"""
    async with redis_lock("auto_draw", ttl=55) as acquired:
        if not acquired:
            return
        due = await get_due_lotteries()
        for lottery in due:
            await execute_draw(bot, lottery)


async def job_reset_quota():
    """每天 00:00 重置每日免费次数"""
    async with redis_lock("reset_quota", ttl=300) as acquired:
        if not acquired:
            return
        from app.models import UserMeta
        async with async_session() as db:
            await db.execute(update(UserMeta).values(free_quota=1))
            await db.commit()
        print("✅ 每日配额已重置")


async def job_check_expiring(bot):
    """每天 02:00 检查即将过期的子号（提前3天提醒）"""
    async with redis_lock("check_expiring", ttl=300) as acquired:
        if not acquired:
            return
        threshold = datetime.now() + timedelta(days=3)
        async with async_session() as db:
            stmt = select(Bot).where(
                Bot.is_master == False,
                Bot.is_active == True,
                Bot.expire_time <= threshold,
                Bot.expire_time > datetime.now(),
            )
            result = await db.execute(stmt)
            bots = list(result.scalars().all())

        for b in bots:
            try:
                await bot.send_message(
                    chat_id=b.owner_id,
                    text=f"⚠️ 您的机器人 @{b.bot_username} 将于 {b.expire_time.strftime('%Y-%m-%d')} 到期，请及时续费。",
                )
            except Exception as e:
                print(f"通知 {b.owner_id} 失败: {e}")
        print(f"✅ 已提醒 {len(bots)} 个即将到期的子号")


def start_scheduler(bot):
    """启动调度器"""
    scheduler.add_job(
        job_auto_draw,
        IntervalTrigger(minutes=1),
        args=[bot],
        id="auto_draw",
        replace_existing=True,
    )
    scheduler.add_job(
        job_reset_quota,
        CronTrigger(hour=0, minute=0),
        id="reset_quota",
        replace_existing=True,
    )
    scheduler.add_job(
        job_check_expiring,
        CronTrigger(hour=2, minute=0),
        args=[bot],
        id="check_expiring",
        replace_existing=True,
    )
    scheduler.start()
    print("✅ 定时任务调度器已启动")
