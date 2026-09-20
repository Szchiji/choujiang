import re
from pydantic_settings import BaseSettings


def sanitize_webhook_secret(value: str) -> str:
    if not value:
        return "lucky_draw_default_secret"
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", value)
    if not cleaned:
        cleaned = "lucky_draw_default_secret"
    return cleaned[:256]


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = "change-me"
    PUBLIC_HOST: str = "http://localhost:8000"
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@db/luckycloud"
    REDIS_URL: str = "redis://redis:6379/0"

    @property
    def admin_ids_list(self):
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    @property
    def safe_webhook_secret(self) -> str:
        return sanitize_webhook_secret(self.WEBHOOK_SECRET)

    class Config:
        env_file = ".env"


settings = Settings()
