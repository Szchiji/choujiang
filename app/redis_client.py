import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from app.config import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@asynccontextmanager
async def redis_lock(key: str, ttl: int = 60):
    lock_key = f"lock:{key}"
    acquired = await redis.set(lock_key, "1", nx=True, ex=ttl)
    try:
        yield acquired
    finally:
        if acquired:
            await redis.delete(lock_key)
