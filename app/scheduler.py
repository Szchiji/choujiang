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


# ==================== 任务 1：自动开奖 ====================

async def job_auto_draw(bot):
    """
    每分钟检查一次：到达开奖时间的活动自动开奖
    使用分布式锁，防止多实例重复执行
    """
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


# ==================== 任务 2：每日重置免费次数 ====================

async def job_reset_quota():
    """每天 00:00 重置所有用户的每日免费次数"""
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


# ==================== 任务 3：检查即将过期的子号 ====================

async def job_check_expiring(bot):
    """每天 02:00 检查即将过期的子号（提前 3 天提醒）"""
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
                            f"请及时续费以免影响使用：\n"
                            f"👉 发送 /buy 查看续费套餐"
                        ),
                        parse_mode="HTML",
                    )
                    sent += 1
                except Exception as e:
                    print(f"通知 {b.owner_id} 失败: {e}")

            print(f"✅ 已提醒 {sent} 个即将到期的子号")
        except Exception as e:
            print(f"❌ 检查到期子号失败: {e}")


# ==================== 任务 4：自动过期子号 ====================

async def job_deactivate_expired():
    """每天 03:00 自动停用已过期的子号"""
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


# ==================== 任务 5：清理 30 天前的旧活动 ====================

async def job_clean_old_data():
    """每天 04:00 清理 30 天前已结束的活动"""
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


# ==================== 启动调度器 ====================

def start_scheduler(bot):
    """启动所有定时任务"""
    # 自动开奖（每分钟）
    scheduler.add_job(
        job_auto_draw,
        IntervalTrigger(minutes=1),
        args=[bot],
        id="auto_draw",
        replace_existing=True,
        max_instances=1,
    )

    # 每日重置配额（00:00）
    scheduler.add_job(
        job_reset_quota,
        CronTrigger(hour=0, minute=0),
        id="reset_quota",
        replace_existing=True,
    )

    # 检查即将过期（02:00）
    scheduler.add_job(
        job_check_expiring,
        CronTrigger(hour=2, minute=0),
        args=[bot],
        id="check_expiring",
        replace_existing=True,
    )

    # 自动停用过期（03:00）
    scheduler.add_job(
        job_deactivate_expired,
        CronTrigger(hour=3, minute=0),
        id="deactivate_expired",
        replace_existing=True,
    )

    # 清理旧数据（04:00）
    scheduler.add_job(
        job_clean_old_data,
        CronTrigger(hour=4, minute=0),
        id="clean_old",
        replace_existing=True,
    )

    scheduler.start()
    print("✅ 定时任务调度器已启动（5 个任务）")
