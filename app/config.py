from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = "change-me"
    PUBLIC_HOST: str = "http://localhost:8000"
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@db/luckycloud"
    REDIS_URL: str = "redis://redis:6379/0"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """
        自动修复 Railway 等平台提供的 DATABASE_URL：
        - postgres://      → postgresql+asyncpg://
        - postgresql://    → postgresql+asyncpg://
        - 移除 ?sslmode=require（asyncpg 不支持这个参数）
        """
        if not v:
            return v
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # 移除 asyncpg 不支持的 sslmode 参数
        if "sslmode=" in v:
            import re
            v = re.sub(r"[?&]sslmode=[^&]*", "", v)
        return v

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def fix_redis_url(cls, v: str) -> str:
        """Railway 的 Redis URL 有时是 redis://default:xxx@host:port"""
        return v

    @property
    def admin_ids_list(self):
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
