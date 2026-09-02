# 公网发布包、平台取舍与验收

## 1. 本阶段交付边界

本阶段完成的是“可部署发布包”和本地生产拓扑验收，还没有替用户创建 Render/Railway 账号、绑定 GitHub、产生账单或获得公网 HTTPS URL。

已经完成：

- `Dockerfile.production` 使用 Node 构建 Expo Web，再把 `dist` 复制到非 root Python 运行镜像；
- FastAPI 同源托管 SPA，浏览器路由回退到 `index.html`，缺失的 JS/WASM 仍返回 404；
- Web 文件统一返回 SQLite WASM 所需的 COOP/COEP 响应头；
- Web 未设置 `EXPO_PUBLIC_API_URL` 时使用 `window.location.origin`，Native 仍保留显式 API URL；
- 容器启动顺序固定为生产预检、Alembic 迁移、演示数据重置、Uvicorn；
- `render.yaml` 描述 Web Service、PostgreSQL、Key Value、动态 Host 和 Secret；
- `scripts/smoke-deployment.mjs` 默认只读检查 HTTPS、SPA、安全头、Live/Ready、注册策略和 404；可选登录会创建会话并在验证身份后立即注销；
- CI 构建后端镜像和同源发布镜像，并断言运行 UID 非 0、Web 与迁移文件存在。

尚未完成：

- 真实 Render Blueprint 创建和首次公网发布；
- 真实平台冷启动、代理 Header、外部延迟与公网 429 验收；
- 真实 Sentry 项目、告警、WAF、验证码、自定义域名和持续可用性探测；
- 免费 PostgreSQL 到期前的数据迁移或付费升级。

部署包可复现并不自动证明某个公网实例正在运行；上线状态仍需以目标环境的 HTTPS、健康检查、备份恢复和监控结果为准。

## 2. 为什么把 Web 与 API 收敛为同源服务

原来的独立静态站方案有三个耦合点：

1. Expo Web 构建时必须知道 API URL；
2. API 又必须提前知道 Web Origin 才能配置 CORS；
3. `expo-sqlite` Web 版依赖 Worker、WASM 和 `SharedArrayBuffer`，静态托管必须为 HTML、JS、Worker 和 WASM 返回 COOP/COEP。

免费作品集优先采用同源拓扑：

```text
Browser / Mobile
      │
      │ HTTPS（托管平台终止 TLS）
      ▼
FastAPI release container
  ├─ /api/v1/* → API routers
  └─ /*         → Expo SPA + WASM/Worker
      │
      ├─ PostgreSQL
      └─ Redis-compatible Key Value
```

好处：

- Web 直接使用当前 Origin，不再出现“先有 Web URL 还是先有 API URL”的循环；
- 浏览器不跨源调用 API，不依赖生产 CORS；
- COOP/COEP、缓存策略和 SPA fallback 都由受测的 Python 代码提供；
- 免费演示只需要一个计算实例。

代价：

- 静态资源不再由独立静态 CDN 服务；
- Web 改动与 API 改动会构建同一镜像；
- 免费 Web Service 休眠时，静态页面也会经历冷启动；
- Native 构建仍必须显式设置 `EXPO_PUBLIC_API_URL`。

当访问量和稳定性要求提高后，可以把静态站拆到 CDN，但需要重新验收安全头、CORS、构建期 URL 和缓存。

## 3. 平台比较与当前选择

### Render：低成本预览环境

Render 的 Blueprint 可以描述 Docker Web Service、PostgreSQL 和 Redis 兼容的 Key Value；Web Service 提供托管 TLS、健康检查和回滚。免费实例适合 hobby/preview，不适合作为长期生产承诺：

- 免费 Web Service 空闲 15 分钟后休眠，唤醒大约需要一分钟；
- 一个 Workspace 每月有 750 个免费实例小时；
- 免费 PostgreSQL 固定 1 GB，30 天后到期且没有备份；
- 免费 Key Value 只在内存中保存，重启会丢失限流状态。

官方依据：

- [Render 免费实例限制](https://render.com/docs/free)
- [Render Web Service 与 TLS](https://render.com/docs/web-services)
- [Render Blueprint 规范](https://render.com/docs/blueprint-spec)
- [Render 发布生命周期](https://render.com/docs/deploys)

Render 的独立 `preDeployCommand` 只对付费 Web Service 开放，所以免费发布包把预检、迁移和演示数据重置放在容器启动门禁中。命令任一步失败，Uvicorn 都不会启动；平台健康检查也不会切入失败实例。数据库迁移已经发生在共享数据库时，应用回滚不会自动回滚 Schema，因此迁移必须保持前后兼容。

### Railway：长期在线升级路径

Railway 支持 Dockerfile、pre-deploy command、健康检查、PostgreSQL/Redis 模板和配置即代码，适合后续把迁移从启动命令中拆出。当前官方价格模型为订阅费加实际资源：

- Free 为每月 1 美元资源额度；
- Hobby 为每月 5 美元，包含 5 美元资源用量；
- 超出包含额度后继续按 CPU、内存、存储和流量计费。

官方依据：

- [Railway 定价](https://docs.railway.com/pricing)
- [Railway 配置即代码](https://docs.railway.com/config-as-code/reference)
- [Railway 健康检查](https://docs.railway.com/deployments/healthchecks)
- [Railway 公网规格与代理 Header](https://docs.railway.com/networking/public-networking/specs-and-limits)

求职投递期间如果需要长期稳定 URL，建议升级到 Railway Hobby 或 Render 付费实例；不要把免费冷启动包装成高可用。

### 为什么暂不选 Fly.io

Fly.io 对 Machine、网络和多区域控制更强，但托管 PostgreSQL、Redis 和运行资源需要更多成本与运维判断。本项目当前目标是用最少平台复杂度证明完整交付链路，而不是展示多区域基础设施，因此先不作为第一选择。

## 4. Render Blueprint 配置说明

`render.yaml` 创建三个资源：

```text
nutripilot-demo       Docker Web Service
nutripilot-postgres   managed PostgreSQL
nutripilot-redis      managed Key Value
```

关键配置：

- 三个资源固定在 Singapore，数据库和 Redis 仅使用内部连接地址；
- Render 的 `postgresql://` 连接串由 Settings 规范化为 SQLAlchemy 的 `postgresql+psycopg://`；
- 应用直接以 `RENDER_EXTERNAL_HOSTNAME` 和 `RENDER_GIT_COMMIT` 作为 Host/Release 的平台回退值；显式 `NUTRIPILOT_*` 配置仍具有更高优先级；
- JWT、AI 凭证加密和限流分别使用三个自动生成的 Secret；
- `NUTRIPILOT_DEMO_RESET_PASSWORD` 使用 `sync: false`，首次创建 Blueprint 时由用户填写；
- `NUTRIPILOT_DEMO_TIMEZONE_OFFSET_MINUTES=480` 让演示种子以中国标准时间确定“今天”，避免 UTC 容器跨日后首页为空；
- 公开注册关闭，AI 使用不产生外部费用的 `rule_based` Provider；
- 免费 Key Value 丢失只会清空短期限流/重置锁，不会丢失 PostgreSQL 主数据。

如果 `nutripilot-demo` 名称已被占用，可以同时修改服务名和数据库、Key Value 的 `fromService.name` 引用。

Render 的内置运行变量不是 Blueprint 中可通过 `fromService.envVarKey` 转发的普通用户环境变量。第一次公网同步曾因尝试转发 `RENDER_EXTERNAL_HOSTNAME` / `RENDER_GIT_COMMIT` 失败；最终将平台兼容集中到 Settings 默认值，并用单测固定显式配置优先、平台变量回退的契约。

## 5. 代理与认证限流的诚实边界

Render 文档说明负载均衡器终止 TLS、容器端口不能被公网直接访问，但没有为当前免费拓扑提供可直接写入项目的入站代理 CIDR。本项目不会猜测 CIDR，也不会盲信客户端可伪造的 Header。

因此首版 Render 免费部署：

- 不传 `--behind-proxy`；
- `NUTRIPILOT_TRUSTED_PROXY_CIDRS=[]`；
- 访客桶安全地退化为平台代理对端聚合桶；
- 账号 HMAC 桶仍按规范化邮箱生效；
- 把访客阈值提高到 300/15 分钟，减少共享代理导致的误限流。

这是 fail-safe：攻击者不能靠伪造 IP 绕过，但可以消耗共享访客预算造成登录拒绝服务。公网验收后仍不能声称“Render 部署已实现真实 IP 隔离”。后续应基于平台明确的 Header 覆写契约实现平台适配器，或在自控 Cloudflare/Ingress 边界验证代理网段。

## 6. 首次发布步骤

创建公网资源会连接个人账号并可能产生费用，所以必须由用户明确授权后执行：

1. 把当前代码提交并推送到用户自己的 GitHub 仓库；
2. 在 Render 选择 New → Blueprint 并连接该仓库；
3. 检查 `render.yaml` 将创建一个免费 Web、一个免费 PostgreSQL 和一个免费 Key Value；
4. 为 `NUTRIPILOT_DEMO_RESET_PASSWORD` 填写至少 10 位的演示密码；
5. 等待构建、迁移、演示种子和 `/api/v1/health/ready` 通过；
6. 复制实际 `https://*.onrender.com` URL；
7. 执行公网冒烟：

```powershell
npm run deploy:smoke -- https://your-service.onrender.com
```

需要验证演示登录时，临时设置环境变量，不把密码作为命令参数或写入仓库：

```powershell
$env:NUTRIPILOT_SMOKE_DEMO_EMAIL = "demo@nutripilot.example"
$env:NUTRIPILOT_SMOKE_DEMO_PASSWORD = "<your-demo-password>"
npm run deploy:smoke -- https://your-service.onrender.com
Remove-Item Env:NUTRIPILOT_SMOKE_DEMO_EMAIL,Env:NUTRIPILOT_SMOKE_DEMO_PASSWORD
```

## 7. 发布验收与回滚

外部验收至少检查：

- `/` 和 `/auth` 返回 HTML；
- COOP 为 `same-origin`，COEP 为 `credentialless`；
- `/live` 和 `/ready` 返回 200；
- `/meta/config` 的 `registration_enabled=false`；
- 不存在的 API 与 WASM 返回 404，而不是 SPA HTML；
- 演示登录返回 `is_demo=true`，`/users/me` 可鉴权；
- 浏览器同步后显示 2023 kcal 个性化目标和当日种子记录；
- 非白名单 Host 为 400；
- Render 冷启动时间、P50/P95 和 429 行为记录到指标文档。

回滚流程：

1. 先判断是镜像、配置、迁移还是外部依赖故障；
2. 配置或镜像故障使用平台回滚到最近成功部署；
3. 数据库迁移只允许 expand/contract，不依赖应用回滚撤销 DDL；
4. 若免费 PostgreSQL 临近 30 天，先导出/迁移数据，再替换连接串；
5. 回滚后重新运行公网冒烟，不能只看平台显示“Live”。

## 8. 本地生产验收记录

2026-07-25 使用真实生产候选镜像、PostgreSQL 17 和 Redis 7.4 验证：

- 最终镜像 77,045,335 bytes，运行身份 `uid=999(nutripilot)`；
- 生产预检返回 `status=ok`；
- Alembic 到 v8，演示重置 `executed=true`；
- 最终部署冒烟 10 项全部通过（含登录、身份和注销）；
- Web 根路径 69 ms，演示登录 84 ms（单次本地样本，不是性能基线）；
- 浏览器登录后约 2 秒同步出 2023 kcal 目标、1790 kcal 当日摄入和 4 条记录；
- 首次启动因 Windows 参数转义破坏 Host JSON，预检在迁移和 Uvicorn 前退出；修复后又用最终镜像主动复测脱敏失败路径；
- 验收后临时容器和临时环境文件已清理，本地演示密码已恢复。

## 9. Render 公网部署验收记录

2026-07-26 已完成真实公网发布：

- 地址：`https://nutripilot-demo.onrender.com`
- 分支：`agent/render-public-deployment`
- 首次完整验收版本：`6ce43ff`
- Render Blueprint：一个 Docker Web Service、一个 PostgreSQL 18、一个 Valkey 8，均为 Free、Singapore；
- 部署状态为 Live，最终一次部署从构建到上线用时 1 分 22 秒；
- 启动日志确认生产预检、Alembic 迁移和演示重置成功，重置锚点为中国标准时间的 `2026-07-26`；
- 公网自动冒烟 10/10 通过：根页、SPA fallback、存活、就绪、注册策略、API/资源 404、演示登录、身份鉴权和注销；
- 单次响应样本：根页 3253 ms、SPA fallback 886 ms、live 571 ms、ready 574 ms、登录 2085 ms、身份 560 ms、注销 571 ms；
- 浏览器登录后显示 1790/2023 kcal 和 4 条当日记录；
- AI 助手通过 Tool Calling 读取当日数据，返回剩余约 233 kcal，并展示 Query 证据、Prompt 版本和 Trace；规则 Provider 本次为 7 ms、0 token。

真实部署发现并修复了三个仅靠本地环境不容易暴露的问题：

1. Render 内置的 `RENDER_EXTERNAL_HOSTNAME` / `RENDER_GIT_COMMIT` 不能作为普通 Blueprint `fromService.envVarKey` 转发。修复方案是由 Settings 直接读取平台运行变量，同时保留显式 `NUTRIPILOT_*` 配置的更高优先级，并用测试固定契约。
2. Render 容器使用 UTC，而浏览器位于 UTC+8。原先用服务器 `date.today()` 生成演示数据，会在北京时间跨日后的八小时内造成“今天没有记录”。修复方案是增加可配置的演示时区偏移，所有 seed/reset 入口统一通过同一函数确定日期，并补充 UTC 跨日边界测试。
3. 演示重置会轮换服务端用户 ID，但同一日期的种子复用确定性 `client_id`。浏览器保留旧账号数据时，新账号增量同步命中跨账号本地主键冲突；隔离条件阻止覆盖，却仍推进游标，造成服务端有 58 条日志而首页为 0。修复方案是在检测到 ID 已被其他账号占用时生成新的本地主键，后续仍通过 `server_id/client_id` 匹配，并增加账号轮换回归测试。

这些公网延迟是单次功能验收样本，不是 P50/P95。Render 免费 Web 长时间无访问后会休眠，首次唤醒可能超过 50 秒；免费 PostgreSQL 也有生命周期和备份限制，因此本部署用于作品集演示，不应宣称为高可用生产系统。
