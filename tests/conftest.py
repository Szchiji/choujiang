import os

# 必须在导入应用模块之前设置，避免真实默认值或真实环境配置泄漏进测试
os.environ["BOT_TOKEN"] = "111:master-test-token"
os.environ["WEBHOOK_SECRET"] = "webhook_test_secret_aaa"
os.environ["ADMIN_API_TOKEN"] = "admin_test_secret_bbb"
os.environ["ADMIN_IDS"] = "1001"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@127.0.0.1:5432/luckycloud_test"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/15"
os.environ["PUBLIC_HOST"] = "http://testserver"
os.environ["WEBHOOK_URL"] = "http://testserver/webhook"

import pytest
from fastapi.testclient import TestClient

from app.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def master_token():
    return os.environ["BOT_TOKEN"]


@pytest.fixture
def webhook_secret():
    return os.environ["WEBHOOK_SECRET"]


@pytest.fixture
def admin_token():
    return os.environ["ADMIN_API_TOKEN"]
