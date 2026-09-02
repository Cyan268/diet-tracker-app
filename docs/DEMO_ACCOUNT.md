# 可复现演示账号与种子数据

## 1. 目标

演示账号让访客无需先录入两周数据，即可体验个性化目标、饮食记录、品牌饮品、趋势统计、AI 周报和只读助手。它不是测试夹具的简单复制，而是一条可重复执行、可安全重置、可解释的数据准备流程。

当前种子版本为 `demo-seed-v1`，以传入的 `anchor_date` 为“今天”，生成：

- 1 个带身高、体重、性别、活动水平和目标的演示用户；
- 58 条覆盖连续 14 天的饮食记录，两周各 7 天都有记录；
- 5 条代表性品牌饮品记录：喜茶、瑞幸、霸王茶姬、Manner 和古茗；
- 2 个用户自定义食品；
- 58 条同步变更，使新设备可以通过现有游标同步链路拉取数据。

数据是产品演示样例，不代表真实用户，也不构成营养或医疗建议。

## 2. 本地创建与重置

先在仓库根目录启动服务：

```powershell
docker compose up -d --build
```

密码只通过进程环境传入，不写入仓库、不作为命令行参数，也不会出现在种子命令的 JSON 输出中：

```powershell
$env:NUTRIPILOT_DEMO_PASSWORD = "replace-with-at-least-10-characters"
docker compose exec -e NUTRIPILOT_DEMO_PASSWORD api `
  python -m app.cli.seed_demo --anchor-date 2026-07-22
Remove-Item Env:NUTRIPILOT_DEMO_PASSWORD
```

默认邮箱是 `demo@nutripilot.example`。如需其他邮箱，可在执行前设置 `NUTRIPILOT_DEMO_EMAIL`，或者传入 `--email`。第二次执行必须显式确认重置：

```powershell
$env:NUTRIPILOT_DEMO_PASSWORD = "replace-with-at-least-10-characters"
docker compose exec -e NUTRIPILOT_DEMO_PASSWORD api `
  python -m app.cli.seed_demo --anchor-date 2026-07-22 --reset-existing
Remove-Item Env:NUTRIPILOT_DEMO_PASSWORD
```

非容器环境可在 `backend` 目录用同一个模块命令执行。生产环境还必须显式传入 `--allow-production`，防止运维误操作；这不是授权机制，生产执行权限仍应由部署平台限制。

## 3. 安全边界

- `users.is_demo` 是数据库中的一等字段。种子命令遇到普通账号邮箱会拒绝执行，即使传入 `--reset-existing` 也不会覆盖。
- 重置会在一个数据库事务中显式删除会话消息、AI 凭证、AI 调用日志、刷新令牌、同步变更、饮食记录、私有食品、资料和旧用户；任一步失败都会整体回滚。
- 重置后创建新的随机用户 ID。旧 Access JWT 中的 subject 不再对应用户，旧 Refresh Token 也已删除，因此两类旧令牌都失效。
- 演示账号不能保存用户 API Key，也不会使用服务端付费 OpenAI Key；AI 分析、助手和周报固定走本地规则 Provider，避免共享账号消耗费用或泄露凭证。
- 客户端会显示演示标记和“请勿填写真实隐私信息”提示，并禁用 API Key 输入。

## 4. 为什么不是数据库 SQL 文件

直接提交一份 SQL dump 虽然快，但会绑定数据库版本，密码摘要和 JSON 字段难维护，也很难复用领域 Schema。当前实现调用应用的密码哈希、Pydantic 请求模型和同步快照结构，数据生成逻辑能由 Pytest 覆盖，迁移后也更容易发现契约漂移。

种子对象使用固定 UUID5，便于同一邮箱、日期和版本下复现；用户 ID 在每次重置时使用 UUID4，专门用于撤销旧登录状态。这两个 ID 策略服务于不同目标。

## 5. 已验证结果

2026-07-22 在 Docker Compose 的 PostgreSQL 17 环境完成了以下验证：

- Alembic 升级到 `20260722_0008`；
- 首次生成 58 条日志和 2 个私有食品，重置后仍各只有一份；
- 重置前后的用户 ID 不同，旧 Access Token 和 Refresh Token 均返回 401；
- API 查询得到 58 条双周日志，当前周和上一周均有 7 个记录日；
- 周报 Provider 为 `rule_based_weekly_report_v1`；
- 演示账号凭证状态始终为未配置，写入 API Key 返回 403。

自动化回归为后端 79 个通过、3 个环境相关跳过、综合覆盖率 80%；前端 19 个套件、56 个测试通过。

Expo Web 浏览器验收还确认：登录后客户端先把云端资料同步到账号隔离的 SQLite，首页使用 2023 kcal、88g 蛋白质等个性化目标；“我的”页显示演示标记、女性 23 岁、165cm、55kg；AI 设置页显示费用隔离提示且保存按钮禁用。

## 6. 公开部署前仍需完成

当前已增加 Redis 写入/AI 限流、资源配额、可配置周期重置、多实例锁、可关闭注册和认证访客限流，但默认开发环境不会自动开启周期重置。多个访客在两次重置之间仍会修改同一份共享数据，配额也不是严格并发硬上限。公开部署前仍需配置真实平台 Secret、代理网段与重置周期，接入 Redis/重置告警，并决定是否改为“每个访客克隆独立沙箱”。完整边界见 [`DEMO_PROTECTION.md`](DEMO_PROTECTION.md)。

## 7. 三分钟功能导览

1. 登录并指出演示账号标记，说明数据可安全重置且不使用付费 Key。
2. 打开资料页，展示身高、体重、活动水平如何计算个性化每日目标。
3. 展示两周记录、品牌饮品和统计趋势。
4. 生成周报，解释“SQL/Python 计算事实，AI 只负责叙事”的边界以及规则降级。
5. 打开助手展示证据卡片，再用架构图说明 JWT 用户隔离、游标同步和 request ID。
6. 主动说明共享账号并发修改、定时重置和公网告警尚未完成，避免把本地验证包装成生产能力。
