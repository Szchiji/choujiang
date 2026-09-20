# 🎯 LuckyDraw Cloud

> **透明抽奖 · 流量分发 · 社群增长平台**
>
> 基于比特币区块链公证的 Telegram 抽奖机器人，支持母号引流 + 付费克隆商业模式。

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)](https://fastapi.tiangolo.com/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.4+-blue.svg)](https://docs.aiogram.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 目录

- [项目简介](#-项目简介)
- [核心特性](#-核心特性)
- [技术架构](#-技术架构)
- [快速开始](#-快速开始)
- [环境变量](#-环境变量)
- [目录结构](#-目录结构)
- [功能说明](#-功能说明)
- [API 文档](#-api-文档)
- [数据库设计](#-数据库设计)
- [部署指南](#-部署指南)
- [开发指南](#-开发指南)
- [常见问题](#-常见问题)
- [路线图](#-路线图)
- [许可证](#-许可证)

---

## 🌟 项目简介

**LuckyDraw Cloud** 是一个面向 Telegram 社群运营者的**透明抽奖平台**。与市面上传统的黑盒抽奖机器人不同，本平台通过**比特币区块链哈希**作为开奖随机种子，任何人都可以独立验证开奖结果的公平性。

同时，平台采用 **「免费母号 + 付费克隆子号」** 的商业模式：

- **免费母号**：每天可创建 1 次抽奖，用于体验和引流
- **付费子号**：一次付费，全部功能无限使用，拥有独立 Bot 身份和后台

---

## ✨ 核心特性

### 🔗 区块链公证开奖
- 使用比特币主链区块哈希作为随机种子
- 开奖结果 **公开、透明、可独立验证**
- 提供区块链浏览器验证链接
- 备用随机源（API 不可用时自动降级）

### 🖥️ Web 可视化创建
- 私聊机器人发送 `/create` 获取专属链接
- 浏览器中完成复杂配置（多奖品、多目标、封面图）
- 移动端完美适配

### 📤 多目标批量发布
- 一次抽奖同时发布到 **多个群组/频道**
- 支持 `t.me/xxx` 链接或 `-100xxx` 数字 ID
- 部分失败不影响其他目标

### 👥 强制多频道关注
- 支持同时绑定 **1~N 个频道**
- **参与时** + **开奖前** 双重校验
- 自动剔除中途取关的用户

### 🏗️ 平台 + 克隆架构
- 母号免费引流，子号独立部署
- 数据完全隔离，互不干扰
- 支持白标（自定义名称、头像、欢迎语）

### 🎁 用户增长系统
- 每日签到，连续签到额外奖励
- 邀请好友，双方各得抽奖次数
- 3 天全功能试用

### 💰 支付集成
- Telegram Stars 支付
- 支持月付、年付、终身三种套餐
- 自动通知管理员处理订单

### 📊 管理后台
- 数据看板（用户、活动、收入）
- 用户管理、订单管理、机器人管理
- 一键审核克隆申请

### 🌐 LuckyDraw 广场
- 所有公开抽奖聚合展示
- 支持关键词搜索
- 为频道主提供额外流量曝光

---

## 🏛️ 技术架构

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram 服务器                          │
└─────────────────────────┬───────────────────────────────────────┘
                          │ Webhook (HTTPS)
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx (HTTPS 终结 + 反向代理)                │
└─────────────────────────┬───────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI + Aiogram (Webhook 入口)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Bot Handlers │  │  Web Routes  │  │  Scheduler   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────┬─────────────────────┬─────────────────────┬───────────┘
          ↓                     ↓                     ↓
    ┌──────────┐          ┌──────────┐          ┌──────────┐
    │PostgreSQL│          │  Redis   │          │Blockchair│
    │  数据存储 │          │队列+锁+限流│          │  BTC API │
    └──────────┘          └──────────┘          └──────────┘
```

### 技术栈

| 组件 | 技术 | 说明 |
| :--- | :--- | :--- |
| **Bot 框架** | Aiogram 3.x | 异步、支持 Webhook |
| **Web 框架** | FastAPI | 高性能、异步、自动文档 |
| **数据库** | PostgreSQL 15+ | 支持 JSON 字段、可靠 |
| **缓存/队列** | Redis 7+ | 分布式锁、限流 |
| **定时任务** | APScheduler | 分布式定时调度 |
| **HTTP 客户端** | httpx | 异步请求 |
| **部署** | Docker Compose | 一键启动 |
| **反向代理** | Nginx | HTTPS、负载均衡 |

---

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 一台公网服务器（用于 Webhook）
- 一个域名（可选，本地测试可用 ngrok）

### 步骤 1：克隆项目

```bash
git clone https://github.com/Szchiji/choujiang.git
cd choujiang
```

### 步骤 2：配置环境变量

```bash
cp .env.example .env
nano .env
```

至少需要填写：

```env
BOT_TOKEN=你的机器人Token
ADMIN_IDS=你的Telegram用户ID
WEBHOOK_URL=https://your-domain.com/webhook
WEBHOOK_SECRET=随机字符串
PUBLIC_HOST=https://your-domain.com
```

### 步骤 3：启动服务

```bash
docker compose up -d --build
```

### 步骤 4：初始化数据库

```bash
docker compose exec app alembic upgrade head
```

### 步骤 5：验证

```bash
curl https://your-domain.com/health
# 应返回 {"status": "ok"}
```

在 Telegram 中私聊你的机器人，发送 `/start` 即可开始使用。

---

## ⚙️ 环境变量

| 变量名 | 必填 | 说明 | 示例 |
| :--- | :---: | :--- | :--- |
| `BOT_TOKEN` | ✅ | Telegram Bot Token | `123456:ABC-DEF...` |
| `ADMIN_IDS` | ✅ | 管理员 Telegram ID（逗号分隔） | `123456789,987654321` |
| `WEBHOOK_URL` | ✅ | Webhook 完整地址 | `https://your-domain.com/webhook` |
| `WEBHOOK_SECRET` | ✅ | Webhook 密钥（随机字符串） | `a1b2c3d4e5f6...` |
| `PUBLIC_HOST` | ✅ | 公网访问地址 | `https://your-domain.com` |
| `DATABASE_URL` | ✅ | PostgreSQL 连接字符串 | `postgresql+asyncpg://user:pass@db:5432/luckycloud` |
| `REDIS_URL` | ✅ | Redis 连接字符串 | `redis://redis:6379/0` |

### 生成随机密钥

```bash
# Linux / macOS
openssl rand -hex 32

# Python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📁 目录结构

```
choujiang/
├── .env.example                    # 环境变量模板
├── .gitignore
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini                     # Alembic 配置
├── main.py                         # FastAPI + Webhook 入口
│
├── alembic/                        # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_init.py
│
├── app/
│   ├── config.py                   # 配置管理
│   ├── database.py                 # 数据库连接
│   ├── models.py                   # ORM 模型
│   ├── blockchain.py               # 区块链抽奖算法
│   ├── message_builder.py          # Telegram 消息构建
│   ├── channel_checker.py          # 频道关注校验
│   ├── lottery_service.py          # 开奖业务逻辑
│   ├── redis_client.py             # Redis 客户端 + 分布式锁
│   ├── scheduler.py                # 定时任务调度器
│   │
│   ├── handlers/                   # Telegram 消息处理器
│   │   ├── start.py                # /start /help
│   │   ├── lottery.py              # /create /my 参与抽奖
│   │   ├── admin.py                # 管理员命令
│   │   ├── checkin.py              # /checkin /invite 签到裂变
│   │   └── payment.py              # /buy /orders 支付
│   │
│   └── web/
│       ├── app.py                  # Web 路由
│       └── static/
│           ├── index.html          # 创建抽奖页面
│           ├── verify.html         # 区块链验证页面
│           ├── plaza.html          # LuckyDraw 广场
│           └── admin.html          # 管理后台
│
├── nginx/
│   └── nginx.conf                  # Nginx 配置
│
└── .github/
    └── workflows/
        └── deploy.yml              # GitHub Actions 自动部署
```

---

## 📚 功能说明

### 用户端功能

#### 1. 创建抽奖

```
用户发送 /create
    ↓
机器人返回专属链接
    ↓
用户在浏览器打开 → 填写表单
    ↓
点击发布 → 机器人自动发送到指定群组/频道
```

**支持的配置：**
- 活动标题、副标题
- 封面图链接（可选）
- 多个奖品（名称 + 数量）
- 多个发布目标（群组/频道）
- 强制关注频道列表
- 开奖方式（定时/满员/即时）

#### 2. 参与抽奖

```
群组中点击"参与抽奖"按钮
    ↓
机器人校验：是否已参与？
    ↓
机器人校验：是否关注了所有频道？
    ↓
写入参与记录 + 更新人数
    ↓
（满员模式下）达到目标自动开奖
```

#### 3. 签到与邀请

| 命令 | 功能 |
| :--- | :--- |
| `/checkin` | 每日签到，连续 7 天 +3 次，连续 30 天 +10 次 |
| `/invite` | 生成专属邀请链接，双方各得 +1 次机会 |
| `/me` | 查看个人配额、签到、邀请统计 |

#### 4. 购买套餐

| 命令 | 功能 |
| :--- | :--- |
| `/buy` | 展示套餐，使用 Telegram Stars 支付 |
| `/orders` | 查看我的订单历史 |

#### 5. 其他命令

| 命令 | 功能 |
| :--- | :--- |
| `/start` | 欢迎信息 + 处理邀请参数 |
| `/help` | 查看所有命令 |
| `/my` | 查看我创建的抽奖 |

---

### 管理端功能

#### Web 后台入口

| 地址 | 功能 |
| :--- | :--- |
| `/create` | 创建抽奖表单 |
| `/plaza` | LuckyDraw 广场（公开） |
| `/admin` | 管理后台（需鉴权） |
| `/verify` | 区块链验证页面 |

#### 管理后台鉴权

所有 `/api/admin/*` 接口需要携带 Header：

```
X-Admin-Token: {WEBHOOK_SECRET}
```

---

### 定时任务

| 任务 | 频率 | 说明 |
| :--- | :--- | :--- |
| 自动开奖 | 每分钟 | 扫描到期的定时开奖活动 |
| 重置配额 | 每天 00:00 | 重置用户每日免费次数 |
| 到期提醒 | 每天 02:00 | 提前 3 天通知即将过期的子号 |
| 停用过期 | 每天 03:00 | 自动停用已过期的子号 |
| 清理旧数据 | 每天 04:00 | 归档 30 天前的已结束活动 |

---

## 🔌 API 文档

### 公共接口

#### `GET /health`

健康检查。

**响应：**
```json
{"status": "ok"}
```

#### `GET /api/plaza`

获取 LuckyDraw 广场的公开抽奖列表。

**参数：**
- `q`（可选）：搜索关键词

**响应：**
```json
{
  "lotteries": [
    {
      "id": 1,
      "title": "周年庆超级抽奖",
      "subtitle": "回馈粉丝",
      "cover_image": "https://...",
      "prizes": [{"name": "iPhone", "count": 1}],
      "participants": 128,
      "countdown": "2天14时23分",
      "bot_link": "https://t.me/your_bot?start=lottery_1"
    }
  ],
  "stats": {
    "total": 100,
    "ongoing": 5,
    "participants": 1024,
    "today": 3
  }
}
```

#### `POST /api/lottery`

创建抽奖（Web 表单提交）。

**请求体：**
```json
{
  "uid": 123456789,
  "title": "周年庆超级抽奖",
  "subtitle": "回馈粉丝",
  "cover_image": "https://...",
  "prizes": [{"name": "iPhone", "count": 1}],
  "targets": ["@my_channel", "-1001234567890"],
  "channels": ["@official_channel"],
  "draw_mode": "time",
  "draw_time": "2026-10-01T20:00"
}
```

---

### 管理接口

所有接口需 Header：`X-Admin-Token: {WEBHOOK_SECRET}`

#### `GET /api/admin/stats`

平台统计数据。

**响应：**
```json
{
  "users": 1284,
  "lotteries": 3421,
  "bots": 89,
  "revenue": 44500
}
```

#### `GET /api/admin/users`

用户列表（最多 200 条）。

#### `GET /api/admin/orders`

订单列表（最多 200 条）。

#### `POST /api/admin/orders/{order_id}/approve`

批准订单。

#### `GET /api/admin/bots`

机器人列表。

---

### Telegram Webhook

#### `POST /webhook`

Telegram 更新入口。

**Header 校验：**
```
X-Telegram-Bot-Api-Secret-Token: {WEBHOOK_SECRET}
```

---

## 🗄️ 数据库设计

### `bots` — 机器人实例

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer | 主键 |
| `owner_id` | BigInteger | 拥有者 Telegram ID |
| `bot_token` | String | Bot Token（母号为空） |
| `bot_username` | String | Bot 用户名 |
| `is_master` | Boolean | 是否为母号 |
| `is_active` | Boolean | 是否启用 |
| `expire_time` | DateTime | 到期时间 |
| `created_at` | DateTime | 创建时间 |

### `lotteries` — 抽奖活动

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer | 主键 |
| `bot_id` | Integer | 所属机器人 |
| `title` | String | 活动标题 |
| `subtitle` | String | 副标题 |
| `cover_image` | Text | 封面图 URL |
| `prizes` | JSON | 奖品列表 |
| `targets` | JSON | 发布目标列表 |
| `channels` | JSON | 强制关注频道 |
| `draw_mode` | String | time / count / instant |
| `draw_time` | DateTime | 定时开奖时间 |
| `target_count` | Integer | 满员开奖人数 |
| `block_hash` | String | 开奖用的区块哈希 |
| `block_height` | Integer | 区块高度 |
| `status` | String | draft / ongoing / ended |
| `is_public` | Boolean | 是否上广场 |
| `winner_list` | JSON | 中奖名单 |
| `created_at` | DateTime | 创建时间 |

### `participants` — 参与记录

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer | 主键 |
| `lottery_id` | Integer | 活动 ID |
| `user_id` | BigInteger | 用户 Telegram ID |
| `username` | String | 用户名 |
| `join_time` | DateTime | 参与时间 |

### `user_meta` — 用户元数据

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `user_id` | BigInteger | 主键 |
| `trial_start` | DateTime | 试用开始 |
| `trial_end` | DateTime | 试用结束 |
| `free_quota` | Integer | 每日免费次数 |
| `extra_credits` | Integer | 额外次数 |
| `sign_in_streak` | Integer | 连续签到天数 |
| `last_sign_in` | DateTime | 上次签到 |
| `referral_count` | Integer | 邀请人数 |

### `clone_applications` — 克隆申请

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer | 主键 |
| `user_id` | BigInteger | 申请人 |
| `bot_name` | String | 机器人名称 |
| `bot_token` | String | Bot Token |
| `plan` | String | monthly / yearly |
| `status` | String | pending / paid / approved / rejected |
| `processed_at` | DateTime | 处理时间 |

### `referrals` — 邀请记录

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer | 主键 |
| `inviter_id` | BigInteger | 邀请人 |
| `invitee_id` | BigInteger | 被邀请人（唯一） |
| `created_at` | DateTime | 创建时间 |

---

## 🚢 部署指南

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆代码
git clone https://github.com/Szchiji/choujiang.git
cd choujiang

# 2. 配置环境变量
cp .env.example .env
nano .env

# 3. 启动
docker compose up -d --build

# 4. 初始化数据库
docker compose exec app alembic upgrade head

# 5. 查看日志
docker compose logs -f app
```

### 方式二：配置 HTTPS

使用 Certbot 自动签发 Let's Encrypt 证书：

```bash
# 安装 Certbot
apt install certbot python3-certbot-nginx -y

# 签发证书
certbot --nginx -d your-domain.com

# 自动续期（Certbot 已自动配置）
systemctl status certbot.timer
```

### 方式三：配置 Nginx

```bash
cp nginx/nginx.conf /etc/nginx/sites-available/choujiang
ln -s /etc/nginx/sites-available/choujiang /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 方式四：GitHub Actions 自动部署

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 值 |
| :--- | :--- |
| `SSH_HOST` | 服务器 IP |
| `SSH_USER` | SSH 用户名 |
| `SSH_KEY` | SSH 私钥 |

之后每次推送到 `main` 分支，GitHub Actions 自动部署。

### 服务器要求

| 项目 | 最低配置 | 推荐配置 |
| :--- | :--- | :--- |
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| 磁盘 | 20 GB | 50 GB |
| 带宽 | 1 Mbps | 5 Mbps |

---

## 💻 开发指南

### 本地开发

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动 PostgreSQL 和 Redis（Docker）
docker compose up -d db redis

# 4. 配置环境变量
cp .env.example .env
# 修改 DATABASE_URL 和 REDIS_URL 为 localhost

# 5. 初始化数据库
alembic upgrade head

# 6. 本地启动（Webhook 需要公网，建议用 ngrok）
uvicorn main:app --reload
```

### 使用 ngrok 本地测试 Webhook

```bash
# 启动 ngrok
ngrok http 8000

# 复制 https 地址到 .env
WEBHOOK_URL=https://xxxx.ngrok.io/webhook
PUBLIC_HOST=https://xxxx.ngrok.io

# 重启应用
uvicorn main:app --reload
```

### 数据库迁移

```bash
# 自动生成迁移（修改 models.py 后）
alembic revision --autogenerate -m "add new table"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

### 代码规范

```bash
# 格式化
black app/
isort app/

# 检查
flake8 app/
mypy app/
```

---

## ❓ 常见问题

### Q1：机器人无法接收消息？

**原因**：Webhook 未正确配置。

**排查**：
```bash
# 检查 Webhook 状态
curl "https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"

# 手动删除 Webhook（重新启动应用后会自动设置）
curl "https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
```

### Q2：无法获取频道成员信息？

**原因**：机器人不是频道管理员。

**解决**：把机器人设为频道的**管理员**，权限至少包括「查看成员」。

### Q3：开奖时提示"获取区块链哈希失败"？

**原因**：Blockchair API 限流或不可用。

**解决**：系统会自动降级使用备用随机源，开奖公告中会标注。

### Q4：支付时提示"provider_token invalid"？

**原因**：Telegram Stars 支付 `provider_token` 必须留空。

**解决**：在 `@BotFather` 中启用支付：`/mybots → 选择机器人 → Payments → Telegram Stars`。

### Q5：数据库连接失败？

**检查**：
```bash
# 查看数据库容器状态
docker compose ps

# 查看数据库日志
docker compose logs db

# 手动测试连接
docker compose exec app python -c "
from app.database import engine
import asyncio
async def test():
    async with engine.connect() as conn:
        print('OK')
asyncio.run(test())
"
```

### Q6：如何修改每日免费次数？

修改 `app/models.py` 中 `UserMeta.free_quota` 的默认值，或直接在数据库中执行：

```sql
UPDATE user_meta SET free_quota = 3 WHERE user_id = 123456;
```

### Q7：如何导出抽奖数据？

```sql
-- 导出所有参与者
SELECT user_id, username, join_time 
FROM participants 
WHERE lottery_id = 1;
```

后续版本会加入 Excel 导出功能。

---

## 🗺️ 路线图

### v1.0（当前版本）

- [x] 区块链公证开奖
- [x] Web 可视化创建
- [x] 多目标发布
- [x] 强制多频道关注
- [x] 每日签到 + 邀请裂变
- [x] Telegram Stars 支付
- [x] LuckyDraw 广场
- [x] 管理后台
- [x] 定时任务调度

### v1.1（规划中）

- [ ] 数据导出 Excel
- [ ] 抽奖模板（一键复用）
- [ ] 多语言支持（中/英）
- [ ] 群组管理员邀请
- [ ] 抽奖数据统计图表

### v1.2（规划中）

- [ ] 多管理员支持
- [ ] 奖品发货追踪
- [ ] 自定义抽奖动画
- [ ] API 开放平台
- [ ] Webhook 事件订阅

### v2.0（远期）

- [ ] 多链支持（ETH、SOL）
- [ ] 去中心化存储（IPFS）
- [ ] DAO 治理
- [ ] 插件市场

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/AmazingFeature`
3. 提交更改：`git commit -m 'Add some AmazingFeature'`
4. 推送分支：`git push origin feature/AmazingFeature`
5. 提交 Pull Request

---

## 📄 许可证

本项目采用 **MIT License**，详见 [LICENSE](LICENSE) 文件。

---

## 📞 联系方式

- **项目地址**：[https://github.com/Szchiji/choujiang](https://github.com/Szchiji/choujiang)
- **问题反馈**：[Issues](https://github.com/Szchiji/choujiang/issues)
- **Telegram**：[@LuckyDrawCloud](https://t.me/LuckyDrawCloud)

---

## 🙏 致谢

- [Aiogram](https://docs.aiogram.dev/) - 优秀的 Telegram Bot 框架
- [FastAPI](https://fastapi.tiangolo.com/) - 高性能 Web 框架
- [Blockchair](https://blockchair.com/) - 比特币区块链数据 API
- [Telegram Stars](https://core.telegram.org/bots/payments-stars) - 支付方案

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给它一个 Star！⭐**

Made with ❤️ by LuckyDraw Cloud Team

</div>
