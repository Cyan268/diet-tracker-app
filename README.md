# NutriPilot

NutriPilot 是一个开源的 AI 饮食记录与个性化营养分析应用。

项目采用 Expo/React Native 前端与 FastAPI 后端，支持离线记录、账号认证、增量同步、自然语言结构化记录、用户自行配置模型 API Key、只读饮食助手和个性化营养周报。服务端使用 PostgreSQL 与 Redis，仓库同时提供本地开发、Render 和单 VPS 容器化部署配置。

## 部署方式

- 本地开发：根目录 `compose.yaml` 与下文的 Expo/FastAPI 启动说明。
- Render：根目录 `render.yaml` 提供同源 Web/API Blueprint。
- 单 VPS：使用 [VPS 部署手册](deploy/README.md)和[发布、迁移与回滚手册](deploy/RELEASE.md)。生产发布使用 Git SHA 和镜像 digest，不在服务器上重新构建镜像。

共享演示账号仅用于体验，可能被定期重置；不要在其中保存真实个人信息、私人饮食数据或个人 API Key。部署者可以通过配置关闭公开注册。

## 当前技术栈

- React Native 0.81 + Expo SDK 54
- TypeScript（strict mode）
- Expo Router
- Expo SQLite
- 基于 `PRAGMA user_version` 的版本化 SQLite 迁移
- FastAPI + Pydantic Settings
- SQLAlchemy 2 异步 ORM + PostgreSQL
- Alembic 数据库迁移
- Redis + Docker Compose（本机联调已验证）
- k6 混合读写性能回归基线
- Open Food Facts API
- React Native Chart Kit

## 当前功能

- 食物和饮品记录、编辑、删除
- 食物本地搜索与 Open Food Facts 联网搜索
- 热量和主要营养素计算
- BMR/TDEE 与每日目标计算
- 个性化目标实时预览与未设置资料引导
- 20+ 主流饮品品牌、100+ 代表产品、品牌/单品搜索和单品级奶基规则
- 饮食提醒和一周趋势统计
- CSV/JSON 数据导出
- Android APK 构建
- FastAPI 注册、登录、Bearer 鉴权与当前用户 API
- Access JWT、Refresh Token 轮换、重放检测与幂等登出
- 用户资料、私有食品创建/搜索、饮食记录 CRUD 与每日统计 API
- 离线写入幂等键、营养快照和乐观并发控制
- OpenAPI 自动生成 TypeScript API 契约
- SecureStore 会话、自动刷新、离线登录与账号隔离
- SQLite v2 Outbox、事件合并、指数退避和自动同步
- 游标增量拉取、删除墓碑和可交互冲突解决
- 登录后云端用户资料双向同步与本地个性化目标刷新
- 用户级 OpenAI API Key 设置、服务端 AES-GCM 加密存储与末四位脱敏展示
- 多轮 Tool Calling 饮食助手、三个用户隔离只读工具、消息持久化与回答证据链
- 个性化 AI 营养周报、双周确定性事实、记录完整度门槛、严格结构化叙事与规则降级
- JSON 结构化日志、`X-Request-ID`、统一异常响应与可选 Sentry 错误监控
- 可原子重置的演示账号、两周种子数据、旧令牌失效与共享账号 AI 费用隔离
- Redis 原子限流、演示资源配额与多实例安全的周期重置
- 可部署关闭的公开注册、登录/注册账号标识限流与 HMAC 脱敏 Redis 键
- 可信代理链解析、访客/IP 与账号双层认证限流、显式 Host 白名单
- 非 root API 容器、生产配置预检与 Docker 镜像 CI

## 项目目标

本项目不是给现有应用简单添加一个聊天框，而是构建一条可靠、可评测的 AI 饮食记录链路：

1. 用户通过自然语言描述饮食；图片分析属于后续能力，当前不处理语音。
2. AI 返回经过 Schema 校验的结构化记录草稿。
3. 系统匹配标准食品数据并展示置信度和待确认信息。
4. 用户确认后，由确定性代码计算营养数据并保存。
5. AI 助手通过 Tool Calling 读取真实数据并生成可解释建议。
6. 系统持续评估准确率、用户修改率、延迟和调用成本。

## 文档导航

- [架构说明](docs/ARCHITECTURE.md)
- [AI 评测、回归基线与复现方式](docs/AI_EVALUATION.md)
- [可追溯 Tool Calling 饮食助手](docs/TOOL_CALLING_ASSISTANT.md)
- [AI 对话状态与消息持久化](docs/CONVERSATION_STATE.md)
- [个性化 AI 营养周报](docs/WEEKLY_REPORT.md)
- [后端可观测性、Sentry 与隐私边界](docs/OBSERVABILITY.md)
- [可复现演示账号、种子数据与安全边界](docs/DEMO_ACCOUNT.md)
- [公共 Demo 限流、配额、自动重置与滥用边界](docs/DEMO_PROTECTION.md)
- [公开入口、认证限流与可信代理边界](docs/AUTH_PERIMETER.md)
- [生产网关、可信代理与部署预检](docs/PRODUCTION_GATEWAY.md)
- [公网发布包、平台取舍与验收](docs/DEPLOYMENT_RELEASE.md)
- [饮品目录的数据边界与维护方式](docs/DRINK_CATALOG.md)
- [PostgreSQL API 性能基线](docs/PERFORMANCE.md)
- [架构决策记录](docs/decisions/ADR-001-product-and-architecture.md)
- [SQLite 迁移决策](docs/decisions/ADR-002-sqlite-migrations.md)
- [后端基础架构决策](docs/decisions/ADR-003-backend-foundation.md)
- [认证令牌轮换决策](docs/decisions/ADR-004-auth-token-rotation.md)
- [离线写入契约决策](docs/decisions/ADR-005-offline-write-contract.md)
- [移动端认证与 Outbox 决策](docs/decisions/ADR-006-mobile-auth-and-outbox.md)
- [游标同步与冲突解决决策](docs/decisions/ADR-007-cursor-sync-and-conflict-resolution.md)
- [同源 Web/API 发布决策](docs/decisions/ADR-008-same-origin-release.md)

## 本地运行

```bash
npm install
cp .env.example .env.local
npm start
```

`EXPO_PUBLIC_API_URL` 必须是设备能够访问的后端地址。Android 模拟器访问宿主机通常使用 `http://10.0.2.2:8000`；真机应填写同一局域网内电脑的 IP，不能使用手机自己的 `127.0.0.1`。

类型检查：

```bash
npm run typecheck
```

一次运行类型检查、Lint 和单元测试：

```bash
npm run check
```

在电脑浏览器中运行完整 Web 预览：

```powershell
docker compose up -d --build
npm run web:preview
```

然后打开 `http://127.0.0.1:8082`。该命令先生成 Web 静态构建，再使用带有 SQLite WebAssembly 所需安全响应头的本地服务器预览。浏览器端 Refresh Token 只保存在当前标签页的 `sessionStorage`，关闭标签页后需要重新登录；移动端仍使用系统 SecureStore。

后端开发与验证命令见 [backend/README.md](backend/README.md)。

构建与验收生产候选镜像：

```powershell
docker build --file Dockerfile.production --tag nutripilot:release-candidate .
npm run deploy:smoke -- https://your-deployment.example
```

Render 免费演示拓扑由根目录的 `render.yaml` 描述。创建真实公网资源前先阅读 [公网发布指南](docs/DEPLOYMENT_RELEASE.md)；该操作需要个人平台账号，并可能涉及免费额度到期或后续费用。

## 已知边界

- 当前 AI 记录入口以文本为主，图片分析和持久化后台 Worker 尚未开放。
- 默认规则 Provider 不产生模型费用；真实模型调用需要用户配置自己的 API Key。
- 共享 Demo 的限流、配额和重置机制不能替代 WAF、验证码或完整账号风控。
- 单 VPS 部署是单机架构，不提供高可用；本机备份不能抵抗服务器或系统盘整体丢失。
- 营养目录中的品牌饮品数据均为估算值，不代表品牌官方配方或所有门店的实时菜单。

## 免责声明

项目中的营养数据和 AI 分析仅用于生活记录与软件工程学习，不构成医疗、诊断或治疗建议。
