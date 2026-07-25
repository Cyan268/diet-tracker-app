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

因此简历当前只能写“实现可复现的生产发布包并完成本地生产拓扑验收”，不能写“已上线公网生产系统”。

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

### Render：零费用面试演示首选

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
- `RENDER_EXTERNAL_HOSTNAME` 通过自引用映射到 `NUTRIPILOT_PLATFORM_EXTERNAL_HOST`，加入 Host 白名单；
- JWT、AI 凭证加密和限流分别使用三个自动生成的 Secret；
- `NUTRIPILOT_DEMO_RESET_PASSWORD` 使用 `sync: false`，首次创建 Blueprint 时由用户填写；
- 公开注册关闭，AI 使用不产生外部费用的 `rule_based` Provider；
- 免费 Key Value 丢失只会清空短期限流/重置锁，不会丢失 PostgreSQL 主数据。

如果 `nutripilot-demo` 名称已被占用，可以同时修改服务名和所有 `fromService.name` 引用。

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

公网指标只有完成真实 Render 部署后才能补充。
