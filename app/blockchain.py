import hashlib
import random
import httpx
from app.redis_client import redis

CACHE_KEY = "btc:latest_block"
CACHE_TTL = 60


async def _fetch_blockchair() -> dict:
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get("https://api.blockchair.com/bitcoin/blocks/latest")
        data = resp.json()
        height = data["data"]["height"]
        target = height - 1
        prev = await client.get(f"https://api.blockchair.com/bitcoin/blocks/{target}")
        prev_data = prev.json()
        return {
            "height": target,
            "hash": prev_data["data"][str(target)]["hash"],
            "source": "blockchair",
        }


async def _fetch_mempool() -> dict:
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get("https://mempool.space/api/blocks/tip/height")
        height = int(resp.text.strip())
        target = height - 1
        hash_resp = await client.get(f"https://mempool.space/api/block-height/{target}")
        return {
            "height": target,
            "hash": hash_resp.text.strip(),
            "source": "mempool",
        }


async def _fetch_blockstream() -> dict:
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get("https://blockstream.info/api/blocks/tip/height")
        height = int(resp.text.strip())
        target = height - 1
        hash_resp = await client.get(f"https://blockstream.info/api/block-height/{target}")
        return {
            "height": target,
            "hash": hash_resp.text.strip(),
            "source": "blockstream",
        }


async def get_latest_block_hash() -> dict:
    """多源获取区块哈希，带 Redis 缓存。失败时返回 fallback。"""
    cached = await redis.get(CACHE_KEY)
    if cached:
        import json
        return json.loads(cached)

    for fetcher in (_fetch_blockchair, _fetch_mempool, _fetch_blockstream):
        try:
            result = await fetcher()
            import json
            await redis.set(CACHE_KEY, json.dumps(result), ex=CACHE_TTL)
            return result
        except Exception as e:
            print(f"区块源 {fetcher.__name__} 失败: {e}")
            continue

    # 全部失败，返回可验证的 fallback（仍确定性）
    import time
    fake = hashlib.sha256(f"fallback_{int(time.time() // 60)}".encode()).hexdigest()
    return {"height": 0, "hash": fake, "source": "fallback", "fallback": True}


def draw_winners(participants: list, prizes: list, block_hash: str, lottery_id: int):
    total_prizes = sum(p["count"] for p in prizes)
    if len(participants) < total_prizes:
        return None

    participant_hash = hashlib.sha256(
        ",".join(str(u) for u in sorted(participants)).encode()
    ).hexdigest()
    seed_str = f"{block_hash}_{lottery_id}_{participant_hash}"
    seed_int = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    rng = random.Random(seed_int)

    shuffled = sorted(participants, key=lambda _: rng.random())
    winners_map = {}
    cursor = 0
    for prize in prizes:
        winners_map[prize["name"]] = shuffled[cursor: cursor + prize["count"]]
        cursor += prize["count"]
    return winners_map
