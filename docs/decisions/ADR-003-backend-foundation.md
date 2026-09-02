# ADR-003：FastAPI 模块化单体与异步数据库基础

- 状态：Accepted
- 日期：2026-07-15

## 背景

移动端需要账号、云同步和服务端 AI 编排。模型密钥、权限和云端真实数据不能继续放在客户端，因此需要后端服务。

## 决策

- 使用 FastAPI 构建模块化单体。
- 使用 Pydantic Settings 从环境变量加载分环境配置。
- 使用 SQLAlchemy 2 `AsyncEngine` 和 psycopg 3 异步访问 PostgreSQL。
- 使用 Session Factory 为每个请求创建独立 `AsyncSession`。
- 使用 Alembic 管理 PostgreSQL Schema，自动生成的迁移必须人工复核。
- 区分 Liveness 和 Readiness，数据库不可用时 Readiness 返回 503。
- `pyproject.toml` 表达允许的依赖范围，lock 文件固定 CI 和镜像使用的精确版本。
- 使用 Docker Compose 描述 API、PostgreSQL 和 Redis，并通过 healthcheck 控制启动顺序。

## 为什么选择异步数据库访问

API 后续会进行数据库、对象存储和模型调用等大量 I/O。异步可以在等待 I/O 时服务其他请求，但它不会让 CPU 密集计算自动变快。每个并发任务必须使用独立 Session，因为 AsyncSession 是有状态的事务对象，不支持并发共享。

## 为什么使用模块化单体

当前规模不需要服务发现、分布式事务和跨服务追踪。模块化单体可以保留清晰边界，同时降低个人项目的部署和调试成本。图片分析 Worker 可以在出现独立扩缩容需求时拆出。

## 当前限制

初次决策时本机尚无 Docker，因此只验证了本地 API、Compose YAML 和 Alembic 离线 SQL。2026-07-15 已安装 Docker Desktop 4.82.0，并验证 PostgreSQL 17、Redis 7.4、API 健康检查、Alembic v1-v4 真实迁移以及日志 CRUD/tombstone 冒烟链路；2026-07-17 又完成三类双请求竞争测试。高负载压力与真机弱网仍属于未验证范围。
