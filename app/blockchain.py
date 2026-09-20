import hashlib
import random
import httpx
from datetime import datetime


async def get_latest_block_hash():
    """获取比特币最新区块哈希（用于抽奖种子）"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.blockchair.com/bitcoin/blocks/latest")
        data = resp.json()
        height = data["data"]["height"]
        target_height = height - 1
        prev_resp = await client.get(
            f"https://api.blockchair.com/bitcoin/blocks/{target_height}"
        )
        prev_data = prev_resp.json()
        return {
            "height": target_height,
            "hash": prev_data["data"][str(target_height)]["hash"],
        }


def draw_winners(participants: list, prizes: list, block_hash: str, lottery_id: int):
    """
    多等级抽奖：先高后低，不重复中奖。
    participants: [user_id, ...]
    prizes: [{"name": "iPhone", "count": 1}, ...]
    """
    total_prizes = sum(p["count"] for p in prizes)
    if len(participants) < total_prizes:
        return None

    seed_str = f"{block_hash}_{lottery_id}_{datetime.now().timestamp()}"
    seed_int = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    rng = random.Random(seed_int)

    shuffled = sorted(participants, key=lambda _: rng.random())
    winners_map = {}
    cursor = 0
    for prize in prizes:
        winners_map[prize["name"]] = shuffled[cursor: cursor + prize["count"]]
        cursor += prize["count"]
    return winners_map
