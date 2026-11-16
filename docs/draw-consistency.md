# 开奖事务与恢复说明

## 保证与边界

- 所有开奖入口使用 `execute_draw`；不依赖 Redis TTL 保证幂等。
- 报名与冻结都锁同一 `lotteries` 行：报名事务先完成则纳入名单，冻结先完成则报名被拒绝。冻结边界是 `ongoing → drawing` 提交，不是定时器时间戳或人数上限；不承诺恰好 target_count 人。
- 冻结后名单不再接受报名。频道过滤和区块请求在数据库事务外执行，避免长事务持锁。
- `drawing` 可恢复，多个任务可能重复计算候选结果，但最终提交再次锁活动行、检查无结果，只允许一份结果生效。只有成功提交者发通知。
- 中奖名单、区块信息、核销码、`ended` 同事务提交；提交失败/取消时全部回滚。已提交终态不能被重复调用或异常处理覆盖。
- 进程在冻结后退出：数据库保留 `drawing`；现有每分钟调度会扫描所有 `drawing` 活动，重试到提交终态。也可再次调用 `manual_draw`。无需手工清锁或改状态。长时间 `drawing` 应查日志及数据库/外部依赖，不要清空中奖名单或核销记录。
- 此方案保证的是一份**已提交结果**，未提交的候选计算可能在恢复时重新取区块；不提供随机源预承诺、公证或 exactly-once 消息。

## 通知恢复限制

数据库提交先于 Telegram 发送。发送失败不回滚、不重抽；公告沿用 Redis 重试队列（队列自身失败仅记录日志），中奖者私信失败仅记录日志。
进程在提交后、发送前退出仍可能漏通知；本轮未引入持久 outbox。管理员需根据已存中奖名单、区块信息、核销码补发**相同**结果，不能通过重跑开奖来补发。Redis 重试可能重复发公告。

## 部署前管理员操作（本次没有部署或修改线上数据）

1. 备份数据库；暂停旧版本写入/开奖，避免新旧进程混跑，旧代码不遵守新行锁协议。
2. 只读核查历史 `participants` 的 `(lottery_id,user_id)` 重复，以及 `prize_claims` 的 `(lottery_id,user_id)` 重复/与中奖名单不匹配的记录。历史异常需人工确认有效结果后另行处理，本补丁不自动删除/修正数据。
3. 在正确迁移基线执行 `alembic upgrade head`，包括原有 `002_unique` 与新增 `005_draw`。有重复记录时唯一约束会失败，必须先审计，不可直接删记录或跳过约束。`create_all` 不会给既有表补约束；未纳入 Alembic 管理的数据库需先核对真实结构与基线，不能盲目 stamp。
4. 启动新版本与调度器；观察 `drawing` 恢复日志。回退代码前确认没有处理中活动，旧版本不认识冻结状态。

无新增环境变量；`drawing` 使用已有 status 字符串列。`005_draw` 添加核销记录 `(lottery_id,user_id)` 唯一约束；报名模型声明与既有 `002_unique` 对齐。此约束遵循当前算法每人最多一奖的行为。

## 独立本地 PostgreSQL 测试

使用 Python 3.11（生产 requirements 锁定版本）：

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest==8.3.3 httpx==0.27.0
# 先启动独立临时 PostgreSQL，并创建 choujiang_draw_test 数据库
TEST_DATABASE_URL=postgresql+asyncpg://TEST_USER@127.0.0.1:55471/choujiang_draw_test \
  .venv/bin/python -m pytest tests/integration -q
.venv/bin/python -m compileall -q app tests alembic
```

**测试会清空并重建测试库的应用表。绝不能指向真实业务数据库。** 测试仅允许 localhost/127.0.0.1 且数据库名严格为 `choujiang_draw_test`，不继承应用生产 DATABASE_URL。
测试使用真实并发数据库连接/行锁，外部区块、频道/Telegram 发送使用隔离替身，不访问真实 Telegram/Redis/公链。
