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
        params.pop("sslmode", None)
        new_query = urlencode(params, doseq=True)
        url = urlunparse(parsed._replace(query=new_query))

    return url


DATABASE_URL = normalize_database_url(settings.DATABASE_URL)


# ==================== 连接参数 ====================

connect_args = {}
if any(host in DATABASE_URL for host in ["railway", "render", "supabase", "neon", "aws"]):
    connect_args = {"ssl": "prefer"}
elif "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL and "@db" not in DATABASE_URL:
    connect_args = {"ssl": "prefer"}


# ==================== 引擎 ====================

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
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
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    await engine.dispose()
