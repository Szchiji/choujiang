import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from app.config import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@asynccontextmanager
async def redis_lock(key: str, ttl: int = 60):
    """
    Redis 分布式锁，防止多实例重复执行定时任务。
    用法：
        async with redis_lock("auto_draw", ttl=60) as acquired:
            if acquired:
                # 执行任务
    """
    lock_key = f"lock:{key}"
    acquired = await redis.set(lock_key, "1", nx=True, ex=ttl)
    try:
        yield acquired
    finally:
        if acquired:
            await redis.delete(lock_key)
