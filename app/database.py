from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# ==================== URL 格式化 ====================

def normalize_database_url(url: str) -> str:
    """
    统一数据库连接串格式：
    - postgres://       → postgresql+asyncpg://
    - postgresql://     → postgresql+asyncpg://
    - 移除 asyncpg 不支持的 sslmode 参数
    """
    if not url:
        return url

    # 1. 统一 scheme
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # 2. 移除 asyncpg 不支持的 query 参数
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        # asyncpg 不认 sslmode，需要去掉
        params.pop("sslmode", None)
        # 重新拼接
        new_query = urlencode(params, doseq=True)
        url = urlunparse(parsed._replace(query=new_query))

    return url


DATABASE_URL = normalize_database_url(settings.DATABASE_URL)


# ==================== 连接参数 ====================

# Railway / 云端数据库通常需要 SSL
connect_args = {}
if any(host in DATABASE_URL for host in ["railway", "render", "supabase", "neon", "aws"]):
    connect_args = {"ssl": "prefer"}
elif "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL and "@db" not in DATABASE_URL:
    # 远程数据库默认启用 SSL
    connect_args = {"ssl": "prefer"}


# ==================== 引擎 ====================

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,       # 断线自动重连
    pool_size=5,              # 连接池大小
    max_overflow=10,          # 溢出连接数
    pool_recycle=1800,        # 30 分钟回收一次连接
    connect_args=connect_args,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI 依赖注入用"""
    async with async_session() as session:
        yield session


async def init_db():
    """首次启动自动建表（生产环境建议用 alembic）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """优雅关闭连接池"""
    await engine.dispose()
