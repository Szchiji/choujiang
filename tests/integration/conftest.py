import os

# Tests must never inherit the application's production database configuration.
os.environ.setdefault("BOT_TOKEN", "123456:TEST_DRAW_TOKEN")
os.environ.setdefault("WEBHOOK_SECRET", "test-draw-webhook-secret")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://choujiang@127.0.0.1:55471/choujiang_draw_test",
)
os.environ["REDIS_URL"] = "redis://127.0.0.1:9/0"
