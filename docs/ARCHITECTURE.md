# 架构说明

## 1. 当前架构

当前应用由离线优先的 Expo 客户端与 FastAPI 模块化单体组成：

```text
Expo 页面 → Feature / Repository → SQLite + Outbox
             ↓ 带鉴权的 HTTP
FastAPI → Auth / Diet / Sync / AI / Assistant / Weekly Report
             ↓
        PostgreSQL + Redis

Expo 食品搜索 → Open Food Facts 公共 API
```

现有能力包括账号认证、离线记录、日志增量同步、用户级加密 AI 凭证、文本解析、本地确认、只读助手和营养周报。

日志写入器会先锁定用户同步状态，再在同一事务中写日志、递增用户序号并追加事件。客户端首次发送前冻结请求，后继意图按顺序排队；同步任务携带账号 owner 与 session epoch，运行期写事务经过同实例 FIFO 门禁。对外同步 API 仍使用 v1 游标，稳定快照恢复、图片私有存储和持久后台 Worker 尚未实现。

## 2. 部署拓扑与扩展方向

[独立 VPS Compose](../deploy/compose.prod.yml)提供 Caddy、API、PostgreSQL 与 Redis 拓扑和显式维护入口。API 生产启动不会自动迁移或重置数据库；Render 启动契约仍独立保留。

下图包含扩展方向；Background Worker、Object Storage 不是当前默认部署组件。

```text
React Native / Expo
  ├─ UI 与表单状态
  ├─ SQLite 本地缓存
  ├─ Outbox 待同步事件
  └─ Typed API Client
             │ HTTPS
             ▼
FastAPI Backend
  ├─ Auth API
  ├─ Diet/Profile/Stats API
  ├─ Sync Service
  ├─ AI Orchestrator
  └─ Background Worker
       ├─ PostgreSQL
       ├─ Redis
       ├─ Object Storage
       ├─ Food Data Provider
       └─ Model Provider
```

## 3. 边界划分

客户端负责：

- 用户交互和输入确认。
- 本地缓存和弱网体验。
- 非敏感、确定性的即时展示计算。
- 上传图片前的压缩和格式检查。

服务端负责：

- 身份认证和数据权限。
- 云端真实数据源。
- 模型密钥、Prompt 和 Provider 管理。
- AI 结构化分析、限流、重试与审计。
- 图片私有存储和生命周期管理。

模型负责：

- 从文本或图片中识别候选食物。
- 提取餐次、份量、做法等非结构化信息。
- 基于工具返回数据生成自然语言解释。

确定性代码负责：

- 营养数值换算。
- BMR/TDEE 和每日目标计算。
- 数据聚合和趋势指标。
- 权限、阈值规则和最终数据写入。

## 4. 关键设计原则

### AI 不直接成为事实数据库

模型可以判断“图片可能是宫保鸡丁”，但正式营养记录必须匹配食品数据源并经用户确认。这样可以减少幻觉并保留可追溯性。

### AI 不可用时核心功能仍可用

手动搜索、记录、营养计算和统计不能依赖模型。AI 是增强链路，不是整个应用的单点故障。

### 离线优先而不是纯在线

现有 SQLite 不是废弃代码，而会演进为本地缓存。客户端写入时同时记录 Outbox 事件，恢复网络后上传，服务端通过幂等键避免重复写入。

### 先模块化单体，再考虑微服务

求职项目不需要为了名词堆砌拆成微服务。第一版使用模块化单体，更容易保证事务、部署和调试；只有在出现明确的独立扩缩容需求时才拆分。

## 5. 客户端数据库迁移

SQLite 使用 `PRAGMA user_version` 保存 Schema 版本。应用启动时只执行高于当前版本的迁移：

```text
读取 user_version
  → 检查应用是否支持该版本
  → 选择待执行迁移
  → BEGIN IMMEDIATE
  → 执行 Schema 修改
  → 更新 user_version
  → COMMIT / 失败 ROLLBACK
```

初始迁移使用幂等的 `CREATE TABLE IF NOT EXISTS`，因此已有旧用户即使表已存在但版本仍为 0，也能在不删除数据的情况下标记为 v1。后续每次 Schema 变化都必须新增迁移，不能修改已经发布的历史迁移。

## 6. 后端当前实现

后端采用模块化单体，并按职责拆分为：

```text
app/api       HTTP 路由与状态码
app/schemas   API 输入输出契约
app/models    SQLAlchemy 持久化模型
app/core      配置、数据库和基础设施
migrations    Alembic 版本迁移
tests         API 与模型测试
```

数据库使用 SQLAlchemy `AsyncEngine`。每个请求通过 Session Factory 获得独立 `AsyncSession`，请求结束后关闭，不能把同一个 Session 共享给并发任务。

健康检查分为：

- Liveness：只证明 API 进程仍能响应，不访问外部依赖。
- Readiness：执行 `SELECT 1` 检查 PostgreSQL；不可用时返回 503，让负载均衡停止发送流量。

容器化集成测试使用 PostgreSQL 17、Redis 7.4 和真实 Alembic 迁移；API 性能场景与解释边界见 [PERFORMANCE](PERFORMANCE.md)。

## 7. 认证与令牌轮换

```text
注册 / 登录
  → Argon2id 哈希或验证（线程池）
  → 15 分钟 Access JWT
  → 30 天随机 Refresh Token
  → 数据库只保存 Refresh Token 的 SHA-256 摘要

刷新请求
  → 按摘要查询并锁定令牌行
  → 旧令牌标记 revoked
  → 同 family_id 创建新令牌
  → 旧令牌再次出现：撤销整个活跃令牌家族
```

普通业务 API 校验 Access JWT 的签名、算法、签发方、受众、类型和时间声明，再加载当前用户；刷新和登出才访问 `refresh_tokens` 状态。令牌有效性校验不查询令牌表，但账号停用仍能通过用户查询即时生效，这是性能与权限时效性的折中。

## 8. 饮食领域与离线写入契约

```text
Expo 本地新增记录
  → 生成稳定 client_id
  → 同一 SQLite 事务写入记录与 Outbox
  → POST /logs
      ├─ 同 user_id + client_id + 同内容：返回已有记录
      ├─ 同 user_id + client_id + 不同内容：409
      └─ 新键：服务端计算/校验营养快照并写入

多设备更新
  → 提交 expected_version
  → UPDATE ... WHERE user_id=? AND id=? AND version=?
      ├─ 影响 1 行：version + 1
      └─ 影响 0 行：409，客户端进入冲突处理
```

核心表包括一对一 `user_profiles`、支持全局与私有数据的 `food_items`，以及带 `client_id`、营养快照和 `version` 的 `food_logs`。所有私有查询在 SQL 层绑定当前 `user_id`，每日统计也只聚合当前用户的数据。

## 9. 移动端认证与类型契约

```text
FastAPI routes / Pydantic schemas
  → backend/openapi.json
  → openapi-typescript
  → src/api/generated/schema.ts
  → AuthSession / 后续 Typed API Client
```

Access Token 只驻留内存；Refresh Token 和最小用户对象作为一个会话写入 SecureStore。App 重启后使用 Refresh Token 轮换恢复 Access Token。并发 API 请求共享同一个刷新 Promise，防止同时使用一次性 Refresh Token。服务端不可达时允许已登录用户进入离线模式；明确的 401 会清除无效会话。

## 10. SQLite Outbox

```text
本地新增 / 编辑 / 删除
  → withWriteTransaction（Native exclusive / Web regular）
      ├─ 修改 food_logs
      └─ 插入或合并 outbox_events
  → 自动/手动同步
      ├─ pending → processing → 成功删除事件
      ├─ 网络错误 → failed + 指数退避
      └─ 409/422 → blocked，等待用户解决
```

SQLite v2 为 `user_profile`、`food_logs` 和 `outbox_events` 增加 `owner_user_id`。旧单机数据由第一个登录账号认领。所有本地查询、统计、导出和队列读取按当前账号过滤，防止退出登录后另一个账号读取上一账号缓存。

同步在认证恢复、App 回到前台、每 60 秒和用户手动操作时触发。进程内使用 single-flight 防止重复 Worker；超过 5 分钟仍处于 `processing` 的事件会被恢复为可重试状态。

## 11. 云端增量拉取与冲突解决

```text
PostgreSQL 业务事务
  ├─ 新增 / 更新 / 删除 food_logs
  └─ 追加 sync_changes（单调递增 cursor）

Expo GET /sync/changes?after=cursor
  → SQLite 写事务（Native exclusive / Web regular）
      ├─ 无本地修改：应用 upsert 或 delete tombstone
      ├─ 有并发修改：写入 sync_conflicts 并阻塞 Outbox
      └─ 整页成功后推进账号独立 cursor
  → lastSyncAt 通知首页和统计重新读取 SQLite
```

upsert 事件保存变更发生时的完整快照，而不是拉取时再查询当前记录；delete 保留 tombstone。服务端通过每用户状态锁使同一用户的日志写入和事件序号保持提交顺序。对外 v1 游标仍没有稳定快照和事件保留期恢复协议，因此客户端不能把增量接口当作永久备份。

冲突页面提供整条记录级二选一：“使用云端”会取消本地 Outbox 并应用远端状态；“保留本机”会把本地事件的基准版本更新到远端最新版本后重试。若远端已经删除，保留本机会将本地记录作为新资源重新创建。该策略不会静默覆盖，但暂不支持字段级自动合并。

## 12. 用户级 AI 凭证保险箱

```text
AI 设置页提交 Key（只提交一次）
  → Bearer JWT 确认当前用户
  → AES-GCM(服务端主密钥派生值, 随机 nonce, AAD=user_id+版本)
  → PostgreSQL 仅保存密文与末四位

AI 分析
  → 按 user_id 读取密文
  → 服务端临时解密
  → OpenAI Responses Provider
  → Schema 校验、有限重试、规则降级、Token 日志
```

客户端不持久化 Key，查询接口也不返回密文或明文。AES-GCM 的 AAD 将凭证与用户绑定，避免数据库中的密文被换到另一个账号后继续使用。生产环境必须替换开发主密钥并使用 HTTPS。由于服务端调用模型时必须解密，此方案属于服务端加密存储，不是端到端加密；未来轮换主密钥时需要增加密钥版本与批量重加密流程。

## 13. 可追溯 Tool Calling 助手

```text
AI 助手页提交问题和 reference_date
  → JWT 得到 current_user.id
  → OpenAI Responses / 本地规则助手
  → 白名单 function_call
      ├─ get_today_summary
      ├─ get_weekly_trend
      └─ search_food
  → 服务端注入 user_id，执行只读领域查询
  → function_call_output 以相同 call_id 回传
  → answer + evidence + trace/Token/延迟/降级状态
```

工具参数不包含 `user_id`，模型不能选择账号；SQL 查询统一绑定当前用户，食品搜索只返回公共食品和当前用户的私有食品。首轮必须调用工具、禁用并行工具调用，最多三轮，避免无依据回答和无限循环。前端将工具摘要作为证据卡片展示。完整边界见 [`docs/TOOL_CALLING_ASSISTANT.md`](TOOL_CALLING_ASSISTANT.md)。

## 14. AI 对话状态与上下文裁剪

```text
assistant_conversations(user_id, title, updated_at)
  └─ assistant_messages(role, sequence, content, evidence, trace_id)

发送新问题
  → JWT 校验会话所有权
  → client_message_id 幂等预检查
  → 读取最近 8 条 / 最多 6,000 字符历史
  → Responses(store=false) 或本地规则助手
  → 当前轮重新调用只读工具
  → AI 调用日志 + 用户/助手消息落库
```

`(conversation_id, sequence)` 保证顺序唯一，`(conversation_id, client_message_id)` 防止普通重试重复保存。同一键配不同正文返回 409。会话详情最多返回最近 100 条消息，避免无界响应；模型上下文只取最近四轮，历史用于理解省略表达而不作为营养事实来源。用户可删除整个会话，消息显式删除且外键级联作为第二层保护。详细取舍见 [`docs/CONVERSATION_STATE.md`](CONVERSATION_STATE.md)。

## 15. 个性化 AI 周报的事实与叙事分层

```text
JWT user_id + end_date
  → SQL 聚合当前 7 天与上一 7 天
  → 确定性 WeeklyReportFacts
      ├─ 记录覆盖率与固定 7 天日均
      ├─ 个性化目标（可空）
      └─ 有完整度门槛的周环比
  → OpenAI Structured Outputs / 本地规则 Provider
  → WeeklyReportNarrative
  → facts + narrative + fingerprint + trace/Token/延迟
```

模型不计算营养数字，也不接触用户 ID 或任意查询能力。只有当前周和上一周均至少记录 4 天时才生成环比；上周基数为零时百分比保持空值。规范化事实会生成 SHA-256 指纹，便于判断报告输入是否变化。无 Key 直接使用本地规则 Provider，真实模型错误则有限重试后降级，界面显式展示 Provider 和警告。完整契约见 [`docs/WEEKLY_REPORT.md`](WEEKLY_REPORT.md)。

## 16. 请求追踪与错误监控

```text
HTTP request
  → 校验/生成 request_id
  → ContextVar 绑定请求上下文
  → FastAPI endpoint
      ├─ 正常/业务错误：结构化完成日志
      └─ 未处理异常：脱敏 500 + 可选 Sentry
  → X-Request-ID response header
```

结构化日志只记录时间、级别、事件、请求 ID、环境、方法、端点函数、状态码和耗时。为避免原始 Query 出现在 Uvicorn access log 中，默认 access log 被关闭。Sentry 只有配置 DSN 才启用，并关闭默认 PII、本地变量和请求正文；`before_send` 再删除请求详情。完整配置、隐私边界和告警待办见 [`docs/OBSERVABILITY.md`](OBSERVABILITY.md)。

## 17. 可重置演示账号

```text
NUTRIPILOT_DEMO_PASSWORD + anchor_date
  → seed_demo CLI 校验环境和账号类型
  → 单个 PostgreSQL 事务
      ├─ 可选：显式删除旧演示用户的全部从属数据
      ├─ 创建 is_demo=true 的新用户并先 flush 父记录
      ├─ 创建资料、私有食品和 58 条双周日志
      └─ 为日志创建 58 条 sync_changes
  → commit 后输出不含密码的计数摘要

演示用户登录
  ├─ syncRemoteProfile 拉取资料并刷新本地个性化目标
  ├─ 客户端显示演示标记和隐私提示
  ├─ AI 凭证读接口固定返回未配置
  ├─ AI 凭证写/删接口返回 403
  └─ AI 功能固定使用本地规则 Provider
```

`is_demo` 是数据库字段而不是邮箱命名约定，因此种子命令不会覆盖普通账号。重置显式轮换用户 ID 并删除 Refresh Token，使旧 Access JWT 和 Refresh Token 同时失效。种子记录使用按版本、邮箱、日期生成的稳定 UUID5，便于复现；用户 ID 使用随机 UUID4，服务于令牌撤销。

用户模型与食品等从属模型只保存显式外键 ID，没有 ORM relationship。真实 PostgreSQL 验收曾发现一次性 flush 不能推断父子插入顺序，因此当前先 flush 用户父记录，再在同一事务中插入从属记录；flush 不等于 commit，后续失败仍会整体回滚。完整运行方式和公开部署限制见 [`docs/DEMO_ACCOUNT.md`](DEMO_ACCOUNT.md)。

资料没有进入日志的游标变更表，因此客户端同步时单独读取 `/users/me/profile`：本地为空时拉取云端，云端为空或本地 `updated_at` 更新时推送本地副本，随后用服务端时间覆盖本地。当前属于基于时间戳的整对象 Last-Write-Wins；客户端时钟漂移和两端同时编辑仍可能选错版本，公开多设备版本应改为服务端版本号或显式冲突解决。

## 18. 公共 Demo 限流、配额与多实例重置

```text
演示写入 / AI 请求
  → JWT 得到 is_demo + rotating user_id
  → Redis Lua: INCR + first PEXPIRE + PTTL（单次原子执行）
      ├─ 未超过动作阈值：继续
      ├─ 超过：429 + Retry-After
      └─ Redis 故障：开发放行 / 生产 503
  → 创建类请求检查 PostgreSQL 资源计数
      ├─ 有容量：执行原领域事务
      └─ 达到上限：403，等待重置

每个 API 实例的 reset loop
  → 等待配置周期
  → Redis SET lock token NX EX ttl
      ├─ 未获锁：本轮跳过
      └─ 获锁：执行单事务 demo seed reset
  → Lua 比较 token 后删除锁
```

限流键只使用用户 UUID 和 `write`/`ai` 动作，不保存邮箱、IP、Query 或正文。共享账号采用总量桶，优先保护数据库资源而非保证访客公平。生产配置必须 fail-closed；普通账号与只读请求不依赖该桶，因此 Redis 不是整个 API readiness 的硬依赖，但需要独立监控。

资源配额保护日志、私有食品、对话和消息。幂等日志/消息先查原请求，再检查新资源容量，避免达到上限后破坏重试。当前计数与写入不是一个带用户锁的原子操作，并发时可能轻微超额；硬配额需要 PostgreSQL advisory transaction lock 或 Redis 原子预留与失败补偿。自动重置的锁使用随机 Token 防止旧持有者误删新锁，TTL 防止死锁，但尚未实现长任务续租。完整配置与验收见 [`docs/DEMO_PROTECTION.md`](DEMO_PROTECTION.md)。

## 19. 公开入口与认证保护

```text
GET /meta/config
  → 仅返回 registration_enabled
  → Expo 决定是否展示注册入口

POST /auth/register
  → 后端注册开关
  → 可信代理链 → 隐私化访客总量桶
  → HMAC-SHA256(action + normalized email)
  → Redis Lua 固定窗口
  → Argon2id + PostgreSQL

POST /auth/login
  → 同样的访客桶 + 隐私化账号桶
  → 统一 401，未知/已知邮箱不分策略
  → 成功后清除登录桶
```

认证与演示限流复用一个 Redis 原子限流器，但使用不同键空间和故障策略。Redis 键不保存原始邮箱或 IP；访客、登录和注册动作经域隔离后得到不同 HMAC。成功登录只清账号桶，不清访客桶。生产环境启用保护时必须 fail-closed。前端配置失败会隐藏注册，但安全边界仍是后端 403。

Uvicorn 保留 TCP 对端；只有对端属于显式可信 CIDR 时，应用才从右向左解析 `X-Forwarded-For`。非法、过长或来自不可信对端的 Header 被忽略。完整配置与验收见 [`docs/AUTH_PERIMETER.md`](AUTH_PERIMETER.md)。

## 20. 生产网关与部署预检

```text
TLS / WAF / Load Balancer
  → Host 白名单
  → 可信代理地址解析
  → FastAPI 非 root 容器
  → PostgreSQL / Redis

发布前
  → Settings 生产安全不变量
  → production_preflight --portfolio --behind-proxy
  → Docker CI 构建 + 非 root UID 断言
  → Alembic migration
  → /live + /ready
```

应用容器不持有 TLS 证书，HTTPS、HSTS、跳转和边缘 DDoS 防护属于托管网关。`TrustedHostMiddleware` 拒绝未允许 Host，生产配置禁止 `*`；作品集预检还检查 HTTPS CORS Origin、关闭注册、保护层、非本地依赖 URL 和可信代理配置。静态预检不会回显 Secret，也不替代真实依赖和公网探测。详见 [`docs/PRODUCTION_GATEWAY.md`](PRODUCTION_GATEWAY.md)。

## 21. 同源作品集发布拓扑

```text
Docker build
  ├─ Node 22: npm ci → Expo Web export
  └─ Python 3.13: FastAPI + Alembic + /app/web

Container start
  → production_preflight --portfolio --single-origin-web
  → alembic upgrade head
  → reset_demo --allow-production
  → uvicorn --no-proxy-headers

HTTPS request
  ├─ /api/v1/* → API
  └─ /* → Expo SPA / WASM / Worker
```

Web 未显式配置 API URL 时使用当前 Origin，消除静态站 URL、API URL 和 CORS 的创建循环。FastAPI 只对无扩展名浏览器路径回退 `index.html`；缺失 API、JS 或 WASM 保持 404。所有 Web 文件带 COOP/COEP，`assets/` 使用一年 immutable 缓存，HTML/metadata 使用 `no-store`。

Render 的 PostgreSQL 连接串在 Settings 层选择异步 psycopg 驱动；Host/Release 在没有显式配置时直接回退读取 Render 内置运行变量，不使用 Blueprint 自引用转发。Secret 由平台生成或首次部署时填写。历史免费拓扑不猜测代理 CIDR，因此不采信转发 Header，访客桶退化为共享平台代理桶，账号桶仍按 HMAC 邮箱隔离。新 VPS 部署必须与该路径隔离，移除启动迁移和重置耦合。完整取舍见 [`docs/DEPLOYMENT_RELEASE.md`](DEPLOYMENT_RELEASE.md)。
