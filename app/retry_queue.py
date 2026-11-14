"""消息发送重试队列（Redis List）"""
import json
from app.redis_client import redis

QUEUE_KEY = "queue:send_retry"


async def enqueue_retry(chat_id, text: str, parse_mode: str = "HTML", reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    await redis.rpush(QUEUE_KEY, json.dumps(payload))


async def process_retries(bot, max_items: int = 20):
    """消费重试队列，由 scheduler 定期调用"""
    processed = 0
    for _ in range(max_items):
        raw = await redis.lpop(QUEUE_KEY)
        if not raw:
            break
        try:
            item = json.loads(raw)
            await bot.send_message(
                chat_id=item["chat_id"],
                text=item["text"],
                parse_mode=item.get("parse_mode", "HTML"),
                disable_web_page_preview=True,
            )
            processed += 1
        except Exception as e:
            # 再入队（简单重试，实际可加次数限制）
            await redis.rpush(QUEUE_KEY, raw)
            print(f"重试发送失败: {e}")
            break
    return processed
