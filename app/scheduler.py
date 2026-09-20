from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update

from app.redis_client import redis_lock
from app.database import async_session
from app.models import Bot, UserMeta, Lottery
from app.lottery_service import get_due_lotteries, execute_draw

scheduler = AsyncIOScheduler()


async def job_auto_draw(bot):
    async with redis_lock("auto_draw", ttl=55) as acquired:
        if not acquired:
            return
        try:
            due = await get_due_lotteries()
            if not due:
                return
            print(f"🔍 扫描到 {len(due)} 个待开奖活动")
            for lottery in due:
                await execute_draw(bot, lottery)
        except Exception as e:
            print(f"❌ 自动开奖任务异常: {e}")


async def job_reset_quota():
    async with redis_lock("reset_quota", ttl=300) as acquired:
        if not acquired:
            return
        try:
            async with async_session() as db:
                await db.execute(update(UserMeta).values(free_quota=1))
                await db.commit()
            print("✅ 每日配额已重置")
        except Exception as e:
            print(f"❌ 重置配额失败: {e}")


async def job_check_expiring(bot):
    async with redis_lock("check_expiring", ttl=300) as acquired:
        if not acquired:
            return
        try:
            threshold = datetime.now() + timedelta(days=3)
            async with async_session() as db:
                rows = (await db.execute(
                    select(Bot).where(
                        Bot.is_master == False,
                        Bot.is_active == True,
                        Bot.expire_time <= threshold,
                        Bot.expire_time > datetime.now(),
                    )
                )).scalars().all()

            sent = 0
            for b in rows:
                try:
                    days_left = (b.expire_time - datetime.now()).days
                    await bot.send_message(
                        chat_id=b.owner_id,
                        text=(
                            f"⚠️ <b>机器人即将到期</b>\n\n"
                            f"🤖 @{b.bot_username}\n"
                            f"📅 到期时间：{b.expire_time.strftime('%Y-%m-%d')}\n"
                            f"⏳ 剩余：<b>{days_left}</b> 天\n\n"
                            f"请及时续费：发送 /buy"
                        ),
                        parse_mode="HTML",
                    )
                    sent += 1
                except Exception as e:
                    print(f"通知 {b.owner_id} 失败: {e}")
            print(f"✅ 已提醒 {sent} 个即将到期的子号")
        except Exception as e:
            print(f"❌ 检查到期子号失败: {e}")


async def job_deactivate_expired():
    async with redis_lock("deactivate_expired", ttl=300) as acquired:
        if not acquired:
            return
        try:
            async with async_session() as db:
                result = await db.execute(
                    update(Bot)
                    .where(
                        Bot.is_master == False,
                        Bot.is_active == True,
                        Bot.expire_time < datetime.now(),
                    )
                    .values(is_active=False)
                )
                await db.commit()
                print(f"✅ 已停用 {result.rowcount} 个过期子号")
        except Exception as e:
            print(f"❌ 停用过期子号失败: {e}")


async def job_clean_old_data():
    async with redis_lock("clean_old", ttl=300) as acquired:
        if not acquired:
            return
        try:
            cutoff = datetime.now() - timedelta(days=30)
            async with async_session() as db:
                result = await db.execute(
                    update(Lottery)
                    .where(
                        Lottery.status == "ended",
                        Lottery.created_at < cutoff,
                    )
                    .values(is_public=False)
                )
                await db.commit()
                print(f"✅ 已归档 {result.rowcount} 个旧活动")
        except Exception as e:
            print(f"❌ 清理旧活动失败: {e}")


def start_scheduler(bot):
    scheduler.add_job(
        job_auto_draw, IntervalTrigger(minutes=1),
        args=[bot], id="auto_draw", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        job_reset_quota, CronTrigger(hour=0, minute=0),
        id="reset_quota", replace_existing=True,
    )
    scheduler.add_job(
        job_check_expiring, CronTrigger(hour=2, minute=0),
        args=[bot], id="check_expiring", replace_existing=True,
    )
    scheduler.add_job(
        job_deactivate_expired, CronTrigger(hour=3, minute=0),
        id="deactivate_expired", replace_existing=True,
    )
    scheduler.add_job(
        job_clean_old_data, CronTrigger(hour=4, minute=0),
        id="clean_old", replace_existing=True,
    )
    scheduler.start()
    print("✅ 定时任务调度器已启动（5 个任务）")
