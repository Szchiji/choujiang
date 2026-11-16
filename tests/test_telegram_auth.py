import pytest

from app.config import sanitize_webhook_secret, settings
from app.telegram_auth import TelegramAuthError, build_init_data, verify_init_data

MASTER = "111:master-test-token"
CLONE = "222:clone-test-token"
USER = {"id": 4242, "username": "alice"}


def test_valid_init_data_succeeds():
    auth_date = 1_700_000_000
    raw = build_init_data(MASTER, USER, auth_date=auth_date)
    parsed = verify_init_data(raw, MASTER, now=auth_date + 10)
    assert parsed["user"]["id"] == 4242
    assert parsed["auth_date"] == auth_date


def test_forged_user_id_is_rejected():
    auth_date = 1_700_000_000
    raw = build_init_data(MASTER, USER, auth_date=auth_date)
    tampered = raw.replace("4242", "9999")
    with pytest.raises(TelegramAuthError) as exc:
        verify_init_data(tampered, MASTER, now=auth_date + 10)
    assert "签名" in exc.value.message


def test_wrong_bot_token_signature_is_rejected():
    auth_date = 1_700_000_000
    raw = build_init_data(MASTER, USER, auth_date=auth_date)
    with pytest.raises(TelegramAuthError) as exc:
        verify_init_data(raw, CLONE, now=auth_date + 10)
    assert "签名" in exc.value.message


def test_expired_init_data_is_rejected():
    auth_date = 1_700_000_000
    raw = build_init_data(MASTER, USER, auth_date=auth_date)
    with pytest.raises(TelegramAuthError) as exc:
        verify_init_data(raw, MASTER, now=auth_date + 24 * 60 * 60 + 1)
    assert "过期" in exc.value.message


def test_sanitize_webhook_secret_has_no_builtin_default():
    assert sanitize_webhook_secret("") == ""
    assert sanitize_webhook_secret("!!!") == ""
    assert "lucky_draw_default_secret" not in sanitize_webhook_secret("")
    assert sanitize_webhook_secret("abc-DEF_12") == "abc-DEF_12"


def test_admin_token_must_differ_from_webhook_secret():
    assert settings.is_admin_api_configured() is True
    original = settings.ADMIN_API_TOKEN
    try:
        settings.ADMIN_API_TOKEN = settings.safe_webhook_secret
        assert settings.is_admin_api_configured() is False
        settings.ADMIN_API_TOKEN = ""
        assert settings.is_admin_api_configured() is False
    finally:
        settings.ADMIN_API_TOKEN = original
