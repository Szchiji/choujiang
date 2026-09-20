FROM python:3.11-slim

# ==================== 环境变量 ====================
# 让 print 立即输出到 Railway 日志（关键！）
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ==================== 系统依赖 ====================
# gcc + libpq-dev 用于编译 asyncpg / psycopg2
# curl 用于健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==================== Python 依赖 ====================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==================== 项目代码 ====================
COPY . .

# ==================== 暴露端口 ====================
# Railway 会自动注入 PORT 环境变量，此处仅声明
EXPOSE 8000

# ==================== 启动命令 ====================
# 使用 sh -c 让 ${PORT} 环境变量展开
# Railway 默认注入 PORT=8080，本地默认 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info"]
