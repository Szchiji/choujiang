"""Telegram Mini App / WebApp initData 校验。

身份只来自签名验证后的 initData，不信任客户端提交的 uid。
子号必须用对应 Bot Token 验签；不把母号签名用在子号请求上。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from app.config import settings

# 默认 24 小时，过期则拒绝
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60


class TelegramAuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class WebAppIdentity:
    user_id: int
    username: Optional[str]
    bot_id: Optional[int]
    is_master: bool


def verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    now: Optional[int] = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """校验 initData HMAC，返回解析后的字段（含 user 对象）。"""
    if not init_data or not bot_token:
        raise TelegramAuthError("缺少登录凭证")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")
    if not received_hash:
        raise TelegramAuthError("登录凭证无效")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise TelegramAuthError("登录凭证签名无效")

    try:
        auth_date = int(parsed.get("auth_date") or 0)
    except (TypeError, ValueError):
        raise TelegramAuthError("登录凭证无效")

    current = int(now if now is not None else time.time())
    if auth_date <= 0 or current - auth_date > max_age_seconds:
        raise TelegramAuthError("登录凭证已过期")
    # 允许少量时钟偏差，但拒绝明显的未来时间戳
    if auth_date - current > 60:
        raise TelegramAuthError("登录凭证无效")

    user_raw = parsed.get("user") or ""
    try:
        user = json.loads(user_raw) if user_raw else {}
    except json.JSONDecodeError:
        raise TelegramAuthError("登录凭证无效")

    try:
        user_id = int(user.get("id"))
    except (TypeError, ValueError):
        raise TelegramAuthError("登录凭证无效")

    if user_id <= 0:
        raise TelegramAuthError("登录凭证无效")

    parsed["user"] = user
    parsed["auth_date"] = auth_date
    return parsed


def build_init_data(
    bot_token: str,
    user: dict[str, Any],
    *,
    auth_date: Optional[int] = None,
    extra: Optional[dict[str, str]] = None,
) -> str:
    """测试辅助：构造合法 initData。不用于生产路径。"""
    fields: dict[str, str] = {
        "auth_date": str(int(auth_date if auth_date is not None else time.time())),
        "query_id": "test-query",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    if extra:
        fields.update(extra)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode
    return urlencode(fields) + f"&hash={digest}"


def extract_init_data(request: Request) -> str:
    init_data = (request.headers.get("X-Telegram-Init-Data") or "").strip()
    if init_data:
        return init_data
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("tma "):
        return auth[4:].strip()
    return ""


def parse_bot_id_header(request: Request) -> Optional[int]:
    raw = (request.headers.get("X-Telegram-Bot-Id") or "").strip()
    if not raw:
        return None
    try:
        bot_id = int(raw)
    except ValueError:
        raise TelegramAuthError("无效的机器人", 403)
    if bot_id <= 0:
        raise TelegramAuthError("无效的机器人", 403)
    return bot_id


async def load_clone_bot_token(bot_id: int) -> str:
    """加载子号明文 Token，仅用于验签。失败不泄露 Token。"""
    from datetime import datetime

    from sqlalchemy import select

    from app.crypto_util import decrypt_token
    from app.database import async_session
    from app.models import Bot

    async with async_session() as db:
        row = (
            await db.execute(select(Bot).where(Bot.id == bot_id))
        ).scalar_one_or_none()

    if not row or row.is_master:
        raise TelegramAuthError("无效的机器人", 403)
    if not row.is_active:
        raise TelegramAuthError("机器人已停用", 403)
    if row.expire_time and row.expire_time < datetime.now():
        raise TelegramAuthError("机器人已过期", 403)

    raw = decrypt_token(row.bot_token or "")
    if not raw or raw.startswith("placeholder_"):
        raise TelegramAuthError("机器人凭证不可用", 403)
    return raw


async def authenticate_webapp(request: Request) -> WebAppIdentity:
    init_data = extract_init_data(request)
    if not init_data:
        raise TelegramAuthError("缺少 Telegram 登录凭证")

    bot_id = parse_bot_id_header(request)
    if bot_id is None:
        token = settings.BOT_TOKEN
        if not token:
            raise TelegramAuthError("服务未配置", 503)
        parsed = verify_init_data(init_data, token)
        is_master = True
    else:
        token = await load_clone_bot_token(bot_id)
        parsed = verify_init_data(init_data, token)
        is_master = False

    user = parsed["user"]
    return WebAppIdentity(
        user_id=int(user["id"]),
        username=user.get("username"),
        bot_id=bot_id,
        is_master=is_master,
    )


async def require_webapp_identity(request: Request) -> WebAppIdentity:
    try:
        return await authenticate_webapp(request)
    except TelegramAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def assert_same_user(claimed_uid: Any, authenticated_user_id: int) -> None:
    """若请求中带了 uid，必须与验签身份一致；未提供或 0 则忽略。"""
    if claimed_uid is None or claimed_uid == "":
        return
    try:
        claimed = int(claimed_uid)
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="身份不匹配")
    if claimed == 0:
        return
    if claimed != int(authenticated_user_id):
        raise HTTPException(status_code=403, detail="身份不匹配")
