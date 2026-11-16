import hmac
import re
from pydantic_settings import BaseSettings


def sanitize_webhook_secret(value: str) -> str:
    """清洗 Webhook secret。空值或无有效字符时返回空字符串，不使用内置默认值。"""
    if not value:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", value)
    return cleaned[:256]


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = ""
    # 管理 API 独立密钥，禁止与 WEBHOOK_SECRET 相同；未配置则管理接口全部拒绝
    ADMIN_API_TOKEN: str = ""
    PUBLIC_HOST: str = "http://localhost:8000"
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@db/luckycloud"
    REDIS_URL: str = "redis://redis:6379/0"

    @property
    def admin_ids_list(self):
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    @property
    def safe_webhook_secret(self) -> str:
        return sanitize_webhook_secret(self.WEBHOOK_SECRET)

    @property
    def admin_api_token(self) -> str:
        return (self.ADMIN_API_TOKEN or "").strip()

    def is_admin_api_configured(self) -> bool:
        token = self.admin_api_token
        if not token:
            return False
        webhook = self.safe_webhook_secret
        if webhook and hmac.compare_digest(token, webhook):
            return False
        return True

    class Config:
        env_file = ".env"


settings = Settings()
