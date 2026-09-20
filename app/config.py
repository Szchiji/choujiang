from pydantic_settings import BaseSettings


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

    class Config:
        env_file = ".env"


settings = Settings()
