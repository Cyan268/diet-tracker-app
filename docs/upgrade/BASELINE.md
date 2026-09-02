# U0-01：升级前基线复核

日期：2026-08-31（Asia/Shanghai）。本报告是升级起点，不是 U1～U6 的完成声明。

## 1. 版本、范围与执行环境

- 代码 SHA：`1991882902d0e8d9befab4c3d3d9f794297e62df`。
- 分支：`agent/render-public-deployment`；本轮未 commit、push、tag、修改 PR 或部署。
- 开始时唯一未跟踪文件为用户提供的 `docs/UPGRADE_DEVELOPMENT_PLAN.md`，没有受版本控制的业务代码改动。
- 已检查 `D:/AGENTS.md`、`D:/milktea_APP/AGENTS.md`、项目根及项目内 `AGENTS.md`，未发现适用文件。
- Windows / PowerShell；Node `v24.15.0`、npm `11.12.1`、项目虚拟环境 Python `3.13.2`。
- Docker CLI `29.6.1` 可用，但 `dockerDesktopLinuxEngine` 命名管道不存在。本轮没有启动容器、连接其他数据库或更改已有服务。
- CI Node 20、生产构建 Node 22、本地 Node 24 存在版本差异，U1 需统一或明确支持矩阵，不能将本地通过等同于全环境通过。
- 新服务器：用户确认已租赁；供应商、地域、规格、系统、域名、SSH 及数据迁移安排尚待提供。购买事实不等于生产操作授权。

本轮只做现有代码审计、质量检查、可用性探测和文档校准；不实施后续协议、不连接 SSH、不调用付费模型、不删除旧 Render 资源。

## 2. 本次实测结果

完整 stdout/stderr 与失败重试记录见 [U0-01-checks.json](evidence/U0-01-checks.json)。环境检查中同一个 shell 执行多条命令时，以输出中的单项结果为准，不仅看最后的 exit code。

| 检查                                             | 本次结果                                                                       | 证据键 / 边界                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| `npm run check`                                  | 通过：TypeScript、零警告 Lint、20 suites / 58 tests                            | `u0Frontend`；Jest 48.633 s，包含并行构建的本机资源影响        |
| `npm run test:coverage`                          | 58 tests；语句 49.23%、分支 41.96%、函数 53.53%、行 50.95%                     | `u0FrontendCoverage`；13.591 s                                 |
| `python -m pytest --cov=app --cov-fail-under=70` | 121 passed、3 skipped；行/分支综合 80.44%，门禁 70% 通过                       | `u0Backend`；124 collected，21.43 s                            |
| Ruff lint / format                               | lint 通过；111 files already formatted                                         | `u0Ruff`                                                       |
| `python -m pip check`                            | No broken requirements found                                                   | `u0PipAlembic`；不等于依赖漏洞审计或锁文件完全一致             |
| Alembic 离线 SQL                                 | 从 base 到 `20260722_0008` 生成成功                                            | `u0PipAlembic`；未实际迁移 PostgreSQL                          |
| `npm run api:types:check`                        | 通过，类型生成后无 Git 差异                                                    | `u0Contract`                                                   |
| 后端实时 OpenAPI 对比                            | 导出结果与已提交 JSON 的 SHA-256 完全一致；23 paths、49 schemas                | `u0Openapi` / `u0Env`                                          |
| Web export 首次                                  | 失败：沙箱 `spawn EPERM`，另有后端临时目录访问警告                             | `u0Web`；不是业务断言失败                                      |
| Web export 正常权限重试                          | 通过：1057 modules、38 assets，含 SQLite WASM 和 Worker                        | `u0WebRetry`；保留颜色环境警告，不删除失败记录                 |
| Compose 静态解析                                 | `docker compose config --quiet` 返回 0                                         | 仅配置解析；没有启动或健康检查                                 |
| Docker / 真实 PostgreSQL / 镜像                  | 引擎未运行；3 个 opt-in 并发测试未执行；未重建或检查本轮镜像 UID、digest、体积 | `u0Env`；不得引用历史 3/3 作为本轮结果                         |
| 旧公网只读探测                                   | 未验证可用：沙箱代理连接失败；正常权限重试根页与 ready 均约 25 s 超时，0 bytes | `u0Public` / `u0PublicRetry`；不能据此确定平台故障或数据库过期 |

前端覆盖率只包含 `jest.config.js` 中的 `src/features/**` 和 `src/services/**`，不覆盖全部页面、数据库仓库或整个 App。后端测试主要使用内存 SQLite、ASGI transport、Mock Provider 和 Fake 限流器；不能验证 PostgreSQL 序列、行锁与真实 Redis Lua 的全部语义。常规 API fixture 还替换了认证/演示 guard，独立保护测试与集成运行必须分开理解。

本次未重新运行 npm 漏洞审计、Expo Doctor、负载测试、真实模型评测、Android 真机、浏览器登录 E2E、备份恢复或新服务器验收。历史结果依然保留，但不标记为当前通过。

## 3. 契约、源码与构建基线

- `app` + `src`：68 个 TS/TSX 文件、10,889 行（包含生成文件、空行和注释，不作为成果指标）；显式 `any` 搜索无匹配。
- SQLite 当前迁移 v3；Alembic head `20260722_0008`，没有新增或改写迁移。
- OpenAPI SHA-256：`29F22CFFEA65E4F218DE1C6D1F6AE29CF0FD91234425D7BA38B6B891AD322F00`。
- 本次 Web 主 bundle `entry-d5b462d1a869028d69790444a106593b.js`：2,126,057 bytes；Worker：138,757 bytes。是未压缩产物体积，不是网络传输体积。
- `dist/index.html` SHA-256：`103162A745B9820A1D58214BF15B29D1223193783F192286DE20B7199CDCBF4A`；`dist` 为忽略的生成目录。
- package-lock、Python runtime/dev lock 与 Dockerfile 的哈希见 `u0Env`，本轮没有更新依赖。
- 历史镜像 77,045,335 bytes / UID 999 是 2026-07-25 验收，不是本轮镜像测量；当前 Dockerfile 用可变基础镜像标签，不能从旧体积推导新镜像。

## 4. 已实现链路与待补边界

| 链路           | 实际代码                                                                   | 本轮核对结论                                                                                                                |
| -------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 文本分析       | `app/ai-add.tsx`、`backend/app/api/routes/ai.py`                           | 同步 POST `food-text:analyze`；草稿保存在页面 useState，没有持久化分析 Job/Draft/Confirmation                               |
| 食品匹配       | `src/features/ai/foodTextAnalysis.ts`                                      | 本地标准名规范化后精确匹配；无服务端别名/Top-K/目录修订；无法换算时阻止保存                                                 |
| AI 保存        | `ai-add.tsx:73`、`logRepository.ts:34`                                     | `addLogs` 在本地事务写日志和普通 create Outbox；不是云端草稿确认。V2 不能同时走这两条保存路径                               |
| 食品与日志身份 | `outboxRepository.ts:8`、`pullSyncService.ts:87`                           | 上行以本地日志 id 为 client_id，传营养快照而不传本地 food_item_id；下行保存 server_id/version，目录尚未映射                 |
| 账号轮换碰撞   | `pullSyncService.ts:149`                                                   | 跨账号本地主键占用时生成新本地 ID；后续靠 server_id 定位。SQLite 没有独立 remote_client_id 列，不能表述成已完整保存三种身份 |
| 服务端写入     | `backend/app/services/diet.py:184`                                         | 单条日志/变更事务和幂等已实现；create/replace/delete 自行 commit，不能循环调用实现多条原子确认                              |
| 增量同步       | `models/sync_change.py:16`、`repositories/diet.py:87`                      | 全局自增 id + `id > after`；没有按用户提交有序序列、游标版本、过期响应或稳定快照                                            |
| Outbox 与认证  | `outboxRepository.ts:39`、`outboxSyncService.ts:157`、`authSession.ts:107` | 有重试与 single-flight，但未冻结曾发送 payload；在途任务未绑定不可变会话代次                                                |
| 事务适配       | `src/db/transactions.ts`                                                   | Native exclusive；Web regular transaction。现有测试验证路由选择，不是实际并发隔离证明                                       |
| 助手与周报     | `services/assistant_tools.py`、`services/weekly_report.py`                 | 可复用只读工具、事实汇总、证据、完整度门槛和规则降级；不等于叙事无幻觉                                                      |
| 部署           | `Dockerfile.production`、`compose.yaml`、`render.yaml`                     | 有同源发布包和历史 Render 验收；当前 Compose 是开发拓扑，发布了 8000/5432/6379，不能直接用于 VPS                            |

更详细的触发条件、优先级、测试缺口与责任任务见 [RISKS.md](RISKS.md)。上述“风险”除明确标注外均为静态审计判断，不冒充已执行故障实验。

## 5. 文档差异校准

| 文件         | 原问题                                                                    | 本轮处理                                                                    |
| ------------ | ------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| README       | 总述仍称后端/同步待补；默认把旧 URL 当当前在线；未区分共享账号和个人 Key  | 改为已实现文本闭环 + 升级中能力；说明公网本轮未验证、演示不允许保存个人 Key |
| ROADMAP      | HTTPS 发布仍未勾选，与 2026-07-26 历史验收矛盾                            | 标记历史 Render 已验收，新服务器仍待实施；链接升级路线                      |
| ARCHITECTURE | 当前仍称纯单机；Web 被描述为独占事务；平台变量仍称自引用                  | 修正当前架构与平台回退，增加同步风险边界，历史图另作目标说明                |
| METRICS      | 前端覆盖率 26.81%、代码行数与后端覆盖率陈旧，多个运行结果没有当前时间边界 | 增加 U0 时间边界并写本次实测；不重写历史表                                  |
| ADR-007      | 全局单调 id 被误读为提交有序，Web 事务描述过强                            | 追加审计注记；新协议 ADR 留给 U0-02，不直接改既有接口                       |
| 升级计划     | 新增计划所有任务待实施                                                    | 仅勾选 U0-01，并指向本报告；其他任务不勾选                                  |

## 6. 下一步门禁

1. U0-02：从下一个可用编号 ADR-009 起，固定唯一确认路径、身份映射、事务边界、Worker 费用未知结果与同步兼容方案。
2. U4-01 是新 AI 批量写入发布的前置：先补响应丢失、会话切换、反序提交测试和修复，再做快照/清理。
3. U1-01 可在本地独立推进：Caddy + 生产 Compose，显式迁移/种子，不沿用每次 API 启动重置数据的行为。真实 PostgreSQL/镜像验收要先恢复本机 Docker 或明确隔离测试环境。
4. SSH、DNS、防火墙、真实迁移、模型评测与公网发布另行确认范围。不得因为 U0-01 完成就跳过这些验收。

U0-01 的“完成”仅表示基线复核与未验证项登记完成，不表示当前服务上线可用或后续高风险缺陷已修复。
