from unittest.mock import patch

import pytest

from app.config import settings
from app.telegram_auth import build_init_data

MASTER = "111:master-test-token"
CLONE = "222:clone-test-token"
AUTH_DATE = 1_700_000_000
NOW = AUTH_DATE + 60
USER_A = {"id": 101, "username": "user_a"}
USER_B = {"id": 202, "username": "user_b"}

class _Result:
    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows or []

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, result=None, execute=None):
        self._result = result
        self._execute = execute

    async def execute(self, stmt):
        if self._execute:
            return await self._execute(stmt)
        return self._result

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None

    def add(self, obj):
        return None


class _CM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False



def _headers(user, token=MASTER, bot_id=None, extra=None):
    init_data = build_init_data(token, user, auth_date=AUTH_DATE)
    headers = {"X-Telegram-Init-Data": init_data}
    if bot_id is not None:
        headers["X-Telegram-Bot-Id"] = str(bot_id)
    if extra:
        headers.update(extra)
    return headers


@pytest.fixture
def frozen_now():
    with patch("app.telegram_auth.time") as t:
        t.time.return_value = NOW
        yield


def test_admin_page_does_not_embed_secrets(client, admin_token, webhook_secret):
    res = client.get("/admin")
    assert res.status_code == 200
    body = res.text
    assert admin_token not in body
    assert webhook_secret not in body
    assert "{{ADMIN_TOKEN}}" not in body
    assert "ADMIN_API_TOKEN" in body or "管理令牌" in body


def test_admin_api_unauthorized_without_token(client):
    res = client.get("/api/admin/stats")
    assert res.status_code == 403


def test_admin_api_rejects_webhook_secret(client, webhook_secret):
    res = client.get("/api/admin/stats", headers={"X-Admin-Token": webhook_secret})
    assert res.status_code == 403


def test_admin_api_rejects_wrong_token(client):
    res = client.get("/api/admin/stats", headers={"X-Admin-Token": "not-the-admin-token"})
    assert res.status_code == 403


def test_admin_api_rejects_when_admin_token_not_configured(client, admin_token):
    original = settings.ADMIN_API_TOKEN
    try:
        settings.ADMIN_API_TOKEN = ""
        res = client.get("/api/admin/stats", headers={"X-Admin-Token": admin_token})
        assert res.status_code == 403
    finally:
        settings.ADMIN_API_TOKEN = original


def test_admin_api_rejects_when_token_equals_webhook(client, webhook_secret):
    original = settings.ADMIN_API_TOKEN
    try:
        settings.ADMIN_API_TOKEN = webhook_secret
        res = client.get("/api/admin/stats", headers={"X-Admin-Token": webhook_secret})
        assert res.status_code == 403
    finally:
        settings.ADMIN_API_TOKEN = original


def test_admin_api_accepts_valid_token(client, admin_token):
    async def fake_execute(stmt):
        return _Result(0)

    with patch("app.web.app.async_session", lambda: _CM(_Session(execute=fake_execute))):
        res = client.get("/api/admin/stats", headers={"X-Admin-Token": admin_token})
    assert res.status_code == 200
    data = res.json()
    assert "users" in data
    assert "revenue" in data


def test_api_me_rejects_missing_init_data(client):
    res = client.get("/api/me")
    assert res.status_code == 401


def test_api_me_rejects_forged_init_data(client, frozen_now):
    raw = build_init_data(MASTER, USER_A, auth_date=AUTH_DATE).replace("101", "202")
    res = client.get("/api/me", headers={"X-Telegram-Init-Data": raw})
    assert res.status_code == 401


def test_api_me_rejects_expired_init_data(client):
    raw = build_init_data(MASTER, USER_A, auth_date=AUTH_DATE)
    with patch("app.telegram_auth.time") as t:
        t.time.return_value = AUTH_DATE + 24 * 60 * 60 + 5
        res = client.get("/api/me", headers={"X-Telegram-Init-Data": raw})
    assert res.status_code == 401


def test_query_uid_cannot_impersonate(client, frozen_now):
    headers = _headers(USER_A)
    res = client.get("/api/me?uid=202", headers=headers)
    assert res.status_code == 403


def test_body_uid_cannot_impersonate(client, frozen_now):
    headers = _headers(USER_A)
    headers["Content-Type"] = "application/json"
    res = client.post(
        "/api/lottery",
        headers=headers,
        json={
            "uid": 202,
            "title": "hack",
            "prizes": [{"name": "x", "count": 1}],
            "targets": ["@channel"],
        },
    )
    assert res.status_code == 403


def test_api_me_uses_initdata_user(client, frozen_now):
    meta = type("Meta", (), {
        "free_quota": 3,
        "extra_credits": 2,
        "sign_in_streak": 4,
        "referral_count": 1,
    })()
    session = _Session(result=_Result(meta))
    with patch("app.web.app.async_session", lambda: _CM(session)):
        res = client.get("/api/me", headers=_headers(USER_A))
    assert res.status_code == 200
    assert res.json()["free_quota"] == 3


def test_cross_bot_initdata_is_rejected(client, frozen_now):
    # 用母号签名，却声称来自子号 9
    async def fake_load(bot_id: int):
        assert bot_id == 9
        return CLONE

    with patch("app.telegram_auth.load_clone_bot_token", fake_load):
        res = client.get("/api/me", headers=_headers(USER_A, token=MASTER, bot_id=9))
    assert res.status_code == 401


def test_clone_initdata_without_bot_id_is_rejected(client, frozen_now):
    res = client.get("/api/me", headers=_headers(USER_A, token=CLONE))
    assert res.status_code == 401


def test_clone_initdata_with_matching_bot_id_succeeds(client, frozen_now):
    meta = type("Meta", (), {
        "free_quota": 1,
        "extra_credits": 0,
        "sign_in_streak": 0,
        "referral_count": 0,
    })()
    session = _Session(result=_Result(meta))

    async def fake_load(bot_id: int):
        assert bot_id == 9
        return CLONE

    with patch("app.telegram_auth.load_clone_bot_token", fake_load), patch(
        "app.web.app.async_session", lambda: _CM(session)
    ):
        res = client.get("/api/me", headers=_headers(USER_A, token=CLONE, bot_id=9))
    assert res.status_code == 200


def test_template_cross_user_is_denied(client, frozen_now):
    with patch("app.web.app.async_session", lambda: _CM(_Session(result=_Result(None)))):
        res = client.get("/api/template/1", headers=_headers(USER_A))
    assert res.status_code == 404
