# 项目指标记录

简历只使用本文件中有采集方法和原始依据的指标。未测量的数据不得写成简历成果。

## 1. 工程质量基线

| 指标                   |               当前值 |                        目标 | 采集方式                             |
| ---------------------- | -------------------: | --------------------------: | ------------------------------------ |
| TS/TSX 源文件数        |                   68 |                      仅记录 | `rg --files app src`                 |
| TS/TSX 代码行数        |             约 9,667 |                      仅记录 | PowerShell 行数统计                  |
| TypeScript strict      |               已开启 |                        保持 | `tsconfig.json`                      |
| 类型检查               |                 通过 |                 CI 持续通过 | `npx tsc --noEmit`                   |
| 自动化测试数           |                   58 |                    持续补充 | `npm test`                           |
| 自动化测试覆盖率       |      行覆盖率 26.81% |            核心业务逻辑优先 | `npm run test:coverage`              |
| CI                     |               已配置 | 类型检查、零警告 Lint、测试 | GitHub Actions                       |
| Expo Doctor            |           18/18 通过 |                    持续通过 | `npx expo-doctor`                    |
| npm 高危/严重漏洞      |                    0 |                    保持为 0 | `npm audit`                          |
| npm 中危公告           | 生产树 13、完整树 14 |        随 Expo SDK 升级处理 | `npm audit --omit=dev` / `npm audit` |
| `src`/`app` 显式 `any` |                    0 |                    保持为 0 | `rg -n "\\bany\\b" src app`          |

## 2. AI 功能指标

| 指标           |             当前值 | 含义                                          |
| -------------- | -----------------: | --------------------------------------------- |
| Schema 合法率  |      规则基线 100% | 26 条样本中返回强类型结构的比例；真实模型待测 |
| 食物识别准确率 |   P/R/F1 均 81.25% | 规则降级 Provider、32 个期望实体              |
| 实体匹配 Top-1 |             未实现 | 第一候选匹配标准食品的正确比例                |
| 用户直接接受率 |             未实现 | 草稿不经修改直接确认的比例                    |
| 平均字段修改率 |             未实现 | 用户修改的 AI 字段占全部字段比例              |
| P50/P95 延迟   | 已采集规则本地基线 | 原始值见版本化 JSON 报告；不可代表公网模型    |
| 请求失败率     |        规则基线 0% | 26 条评测样本；真实模型待测                   |
| 单次调用成本   |     规则基线不适用 | 真实模型需显式配置已核对单价                  |

## 3. 系统指标

| 指标         |                                                      当前值 | 目标方向           |
| ------------ | ----------------------------------------------------------: | ------------------ |
| API P95 延迟 | 本地基线：日志读 27.29 ms、同步读 31.73 ms、日志写 38.32 ms | 上线后接入持续监控 |
| 同步成功率   |                                                      未实现 | 弱网和重复请求测试 |
| 崩溃率       |                                                      未采集 | 接入错误监控后记录 |
| 冷启动时间   |                                                      未采集 | 真机测量           |

## 3.1 后端工程基线

| 指标                       |                                                        当前值 | 采集方式                                     |
| -------------------------- | ------------------------------------------------------------: | -------------------------------------------- |
| 后端测试                   |                                      121 个通过、3 个可选跳过 | `pytest`                                     |
| 后端行/分支综合覆盖率      |                                                        80.50% | 发布候选包 `pytest --cov=app`                |
| Ruff                       |                                                      0 个问题 | `ruff check app tests migrations scripts`    |
| Python 依赖完整性          |                                                          通过 | `python -m pip check`                        |
| Alembic 离线迁移           |                                            v1-v8 SQL 生成成功 | `alembic upgrade head --sql`                 |
| 认证 API 行为              |                    注册、登录、鉴权、轮换、重放检测、登出通过 | SQLite 集成测试                              |
| PostgreSQL 并发正确性      |                                              3 个竞争测试通过 | opt-in Pytest + Docker PostgreSQL            |
| PostgreSQL API 性能基线    | 2,950 请求、97.61 req/s、错误率 0%；三个接口 P95 均小于 40 ms | k6 30 秒混合负载；详见 `docs/PERFORMANCE.md` |
| 饮食领域 API               |                           资料、食品、日志 CRUD、每日统计通过 | SQLite 集成测试                              |
| 数据隔离                   |                                私有食品与饮食记录跨用户不可见 | 双用户 API 集成测试                          |
| 离线重试契约               |                          同键同内容返回原记录，同键异内容 409 | 幂等集成测试                                 |
| 乐观并发控制               |                     过期 `expected_version` 更新/删除返回 409 | API 集成测试                                 |
| FastAPI 根路由             |                                                      HTTP 200 | Uvicorn 本地冒烟测试                         |
| Liveness                   |                                                      HTTP 200 | `/api/v1/health/live`                        |
| Readiness（无 PostgreSQL） |                                                      HTTP 503 | `/api/v1/health/ready`                       |
| Docker Compose             |                        3 个服务运行，PostgreSQL/Redis healthy | `docker compose ps`                          |
| 真实 PostgreSQL 迁移       |                                            Alembic v1-v8 成功 | 容器日志 + `alembic_version` 查询            |
| PostgreSQL API 冒烟        |             日志 CRUD、同步、演示账号重置和旧令牌失效链路通过 | 本地 HTTP 链路                               |
| 演示数据可复现性           |                58 条双周日志、2 个私有食品；两周各 7 个记录日 | CLI + PostgreSQL API 冒烟                    |
| 演示账号滥用保护           |                AI 200/200/429；日志配额 403；第二重置实例跳过 | Redis 7.4 + PostgreSQL 17 + Docker API 冒烟  |
| 认证入口保护               |        同访客轮换邮箱 401/401/429；异访客 401；账号成功后清桶 | Redis 7.4 + PostgreSQL 17 + Docker API 冒烟  |
| 代理与 Host 边界           |                 可信链右向左解析；伪造前缀无效；非法 Host 400 | 单测 + Docker API 冒烟                       |
| API 容器身份               |                                 `uid=999(nutripilot)` 非 root | `docker compose exec api id`                 |
| 生产配置预检               |                    Portfolio + Proxy 模拟生产配置 `status=ok` | `python -m app.cli.production_preflight`     |
| OpenAPI Path               |                                                            23 | FastAPI `app.openapi()`                      |
| 客户端生成契约             |                                               已生成并进入 CI | `npm run api:types`                          |
| SQLite Schema              |                                                            v3 | `PRAGMA user_version`                        |
| 移动认证状态机             |                                              6 个关键分支通过 | Jest `authSession.test.ts`                   |
| Outbox/账号隔离            |                                              8 个相关测试通过 | Jest migration/outbox/isolation tests        |

## 3.2 公网部署验收

2026-07-26 在 Render Singapore 免费方案完成真实公网发布。以下延迟均为部署完成后的单次验收样本，只用于证明链路可用，不代表 P50/P95 性能基线。

| 项目           | 结果                                                                                                 |
| -------------- | ---------------------------------------------------------------------------------------------------- |
| 公网地址       | `https://nutripilot-demo.onrender.com`                                                               |
| 发布版本       | Git commit `6ce43ff`                                                                                 |
| 资源           | Docker Web Service Free、PostgreSQL 18 Free、Valkey 8 Free                                           |
| 部署状态       | Live，构建与启动共 1 分 22 秒                                                                        |
| 启动链路       | 生产配置预检通过、Alembic 迁移通过、演示数据按 `2026-07-26`（UTC+8）重置                             |
| 公网自动冒烟   | 10/10 通过：根页、SPA fallback、存活、就绪、注册策略、404、演示登录、身份鉴权、注销                  |
| 单次 HTTP 样本 | 根页 3253 ms；SPA 886 ms；live 571 ms；ready 574 ms；登录 2085 ms；身份 560 ms；注销 571 ms          |
| 浏览器数据验收 | 2026-07-26 显示 1790/2023 kcal、4 条当日记录，蛋白质/脂肪/碳水等目标与同步数据正常                   |
| AI 助手验收    | Tool Calling 读取当日记录并返回剩余约 233 kcal；规则 Provider 7 ms、0 token，显示证据、Prompt、Trace |
| 尚未采集       | 免费实例休眠后的真实冷启动分布、持续压测、公网 P50/P95、外部 OpenAI Provider 延迟与费用              |

## 4. 指标变更记录

每次记录应包含日期、代码版本、测试环境、样本规模和原始结果位置。

| 日期       | 版本                       | 指标                         | 结果                                                                                                                                                                              | 原始依据                                                                 |
| ---------- | -------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 2026-07-15 | 当前工作区                 | TypeScript 检查              | 通过                                                                                                                                                                              | 本地执行 `npx tsc --noEmit`                                              |
| 2026-07-15 | Phase 0                    | 自动化测试                   | 3 个套件、9 个测试通过                                                                                                                                                            | `npm test`                                                               |
| 2026-07-15 | Phase 0                    | 行覆盖率                     | 26.81%                                                                                                                                                                            | `npm run test:coverage`                                                  |
| 2026-07-15 | Phase 0                    | Expo 项目检查                | 18/18 通过                                                                                                                                                                        | `npx expo-doctor`                                                        |
| 2026-07-15 | Phase 0                    | npm 依赖漏洞                 | 0                                                                                                                                                                                 | `npm audit`                                                              |
| 2026-07-15 | Phase 0                    | 自动化测试                   | 4 个套件、13 个测试通过                                                                                                                                                           | `npm test`                                                               |
| 2026-07-15 | Phase 0                    | 显式 `any`                   | `src`/`app` 中为 0                                                                                                                                                                | `rg` 静态搜索                                                            |
| 2026-07-15 | Phase 1                    | 后端测试                     | 6 个通过，覆盖率 93.88%                                                                                                                                                           | Pytest + Coverage                                                        |
| 2026-07-15 | Phase 1                    | API 冒烟测试                 | Root/Live 200，Ready 503                                                                                                                                                          | 本地 Uvicorn，无 PostgreSQL                                              |
| 2026-07-15 | Phase 1 Auth               | 后端自动化测试               | 19 个通过，覆盖率 82.56%                                                                                                                                                          | Pytest + SQLite 集成测试                                                 |
| 2026-07-15 | Phase 1 Auth               | Alembic 离线迁移             | 用户表 v1、刷新令牌表 v2 SQL 生成成功                                                                                                                                             | PostgreSQL 方言离线 SQL                                                  |
| 2026-07-15 | Phase 1 Domain             | 后端自动化测试               | 27 个通过，覆盖率 79.18%                                                                                                                                                          | Pytest + SQLite 集成测试                                                 |
| 2026-07-15 | Phase 1 Domain             | 数据隔离与离线写入契约       | 双用户隔离、幂等重试、版本冲突通过                                                                                                                                                | API 集成测试                                                             |
| 2026-07-15 | Phase 1 Mobile             | 移动端自动化测试             | 8 个套件、27 个测试通过                                                                                                                                                           | Jest                                                                     |
| 2026-07-15 | Phase 1 Mobile             | Expo Doctor                  | 18/18 通过                                                                                                                                                                        | `npx expo-doctor`                                                        |
| 2026-07-15 | Phase 1 Mobile             | npm 安全审计                 | 高危/严重 0；生产树中危 13                                                                                                                                                        | 非破坏性 `npm audit fix` 后复核                                          |
| 2026-07-15 | Phase 1 Mobile             | OpenAPI 契约                 | 13 Paths，导出文件与应用一致                                                                                                                                                      | SHA-256 比对 + 类型生成                                                  |
| 2026-07-15 | Phase 1 Sync               | 后端自动化测试               | 29 个通过，覆盖率 79.48%                                                                                                                                                          | Pytest + Coverage                                                        |
| 2026-07-15 | Phase 1 Sync               | 移动端自动化测试             | 10 个套件、33 个测试通过                                                                                                                                                          | Jest                                                                     |
| 2026-07-15 | Phase 1 Sync               | 增量同步契约                 | 14 Paths、PostgreSQL v4、SQLite v3                                                                                                                                                | OpenAPI + Alembic + Jest                                                 |
| 2026-07-15 | Phase 1 Runtime            | Docker Compose               | API、PostgreSQL 17、Redis 7.4 运行；依赖 healthy                                                                                                                                  | `docker compose ps`                                                      |
| 2026-07-15 | Phase 1 Runtime            | 真实 PostgreSQL 冒烟         | v4 迁移、注册、日志 v1→v2、删除 tombstone 通过                                                                                                                                    | HTTP + psql + Redis PING                                                 |
| 2026-07-17 | Phase 1 Concurrency        | PostgreSQL 并发正确性        | 幂等新增、乐观锁更新、Refresh Token 重放 3/3 通过                                                                                                                                 | `NUTRIPILOT_POSTGRES_E2E=1 pytest tests/test_postgres_concurrency.py -v` |
| 2026-07-17 | Phase 1 Performance        | PostgreSQL API 本地基线      | 2,950 请求、97.61 req/s、错误率 0%；读日志/同步/写日志 P95 为 27.29/31.73/38.32 ms                                                                                                | `load-tests/results/postgres-local-baseline.json`                        |
| 2026-07-17 | Phase 1 Web                | 浏览器端到端冒烟             | 注册/登录、SQLite 记录、107 kcal 汇总、统计页和 Outbox 云同步通过                                                                                                                 | Expo Web 静态构建 + 本地浏览器 + API 日志                                |
| 2026-07-17 | Phase 1 Web                | 移动端自动化测试             | 11 个套件、35 个测试通过；新增 Web/Native 事务适配测试                                                                                                                            | `npm run check`                                                          |
| 2026-07-17 | Phase 2 Text AI            | 结构化记录首版               | 后端 33 个通过、3 个可选跳过；前端 14 个套件、43 个测试通过                                                                                                                       | `pytest` + `npm run check`                                               |
| 2026-07-17 | Phase 2 AI Runtime         | 模型调用可靠性与可观测性     | 后端 42 个通过、3 个可选跳过；前端 14 个套件、43 个测试通过；Alembic v5 SQL 生成成功                                                                                              | HTTP Mock + Pytest + Jest + Alembic                                      |
| 2026-07-18 | Phase 2 Credentials        | 用户级 AI 凭证保险箱         | 后端 50 个通过、3 个可选跳过；前端 14 个套件、43 个测试通过；真实 PostgreSQL v6 与 Web CRUD 验收通过                                                                              | AES-GCM 单测 + API 集成测试 + Docker + 浏览器                            |
| 2026-07-19 | Phase 3 AI Evals           | 规则降级抽取质量基线         | 26 条/32 实体；Schema 100%；P/R/F1 81.25%；整例完全正确率 65.38%；后端 52 通过、3 跳过                                                                                            | `backend/evals/reports/rule_based_v1.json` + Pytest 回归门禁             |
| 2026-07-19 | Phase 3 Assistant          | 可追溯 Tool Calling 助手     | 3 个用户隔离只读工具；后端 58 通过、3 跳过、覆盖率 81%；前端 15 个套件/45 个测试；每日与七天趋势浏览器验收通过                                                                    | Pytest + Jest + OpenAPI 契约 + Expo Web/API 端到端验证                   |
| 2026-07-20 | Phase 3 Conversation       | 多轮对话与消息持久化         | PostgreSQL v7；后端 62 通过、3 跳过、覆盖率 79%；前端 16 个套件/48 个测试；两轮追问、双会话切换与刷新恢复通过                                                                     | Pytest + Jest + PostgreSQL 迁移 + Expo Web/API 端到端验证                |
| 2026-07-21 | Phase 3 Weekly Report      | 个性化 AI 营养周报           | 22 Paths/48 Schemas；后端 68 通过、3 跳过、覆盖率 78%；前端 17 个套件/51 个测试；Web 构建与 PostgreSQL 双周事实/指纹/trace 冒烟通过                                               | Pytest + HTTP Mock + Jest + OpenAPI + Expo Web + PostgreSQL API 冒烟     |
| 2026-07-22 | Phase 4 Observability      | 请求追踪与错误监控           | 后端 75 通过、3 跳过、覆盖率 79%；JSON 日志、统一 request ID、脱敏 500 和可选 Sentry SDK；Docker 响应头/日志/Query 不落日志验收通过                                               | Pytest + 隐私回归测试 + Docker/PostgreSQL + curl + 容器日志检查          |
| 2026-07-22 | Phase 4 Demo Account       | 可复现演示账号与种子数据     | 后端 79 通过、3 跳过、覆盖率 80%；前端 19 套件/56 测试；PostgreSQL v8；58 条双周日志；重置后旧 Access/Refresh Token 401、Key 写入 403；Web 个性化资料与演示标记通过               | Pytest + Jest + Alembic + Docker/PostgreSQL CLI/API + Expo Web 冒烟      |
| 2026-07-22 | Phase 4 Demo Protection    | Redis 限流、配额与周期重置   | 后端 88 通过、3 跳过、覆盖率 80%；AI 200/200/429、Retry-After 60；日志配额 403；锁被占用时第二实例不执行；限流键不含邮箱                                                          | Pytest + Redis Lua Fake + Docker/PostgreSQL/Redis CLI/API 冒烟           |
| 2026-07-23 | Phase 4 Auth Perimeter     | 公开注册开关与认证限流       | 23 Paths/49 Schemas；后端 97 通过、3 跳过、覆盖率 81%；前端 20 套件/57 测试；注册 403、登录 401/401/429、Retry-After 60；HMAC 键不含邮箱；成功登录清桶；Web 动态隐藏/恢复注册入口 | Pytest + Jest + OpenAPI + Docker/PostgreSQL 17/Redis 7.4 + 浏览器冒烟    |
| 2026-07-25 | Phase 4 Production Gateway | 可信代理、访客限流与部署预检 | 后端 109 通过、3 跳过、覆盖率 82%；前端 20 套件/57 测试；同访客轮换邮箱 401/401/429、异访客 401；Host 400；2 个访客/3 个账号脱敏键；非 root UID 999；生产预检 ok                  | Pytest + Jest + Docker/PostgreSQL 17/Redis 7.4 + 静态预检                |
| 2026-07-25 | Phase 4 Release Package    | 同源生产镜像与发布验收       | 后端 119 通过/3 跳过/覆盖率 80.50%，前端 20 套件/57 测试；77,045,335-byte 镜像、UID 999；部署脚本 10/10；浏览器约 2 秒同步 2023 kcal 目标、1790 kcal 与 4 条记录；无公网指标      | Pytest + Jest + 多阶段 Docker + PostgreSQL 17/Redis 7.4 + 浏览器         |
| 2026-07-26 | Phase 4 Public Deployment  | Render 公网发布与端到端验收  | 后端 121 通过/3 跳过，前端 20 套件/58 测试；Render Free 三资源 Live；公网冒烟 10/10；修复重置账号复用确定性 ID 导致的跨账号本地主键碰撞；浏览器同步 1790/2023 kcal 与 4 条记录    | Render 部署日志 + 公网 smoke 脚本 + 应用内浏览器端到端验证               |
