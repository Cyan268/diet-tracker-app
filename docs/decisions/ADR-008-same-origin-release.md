# ADR-008：免费作品集采用同源 Web/API 发布镜像

- 状态：Accepted
- 日期：2026-07-25

## 背景

Expo Web 使用 `expo-sqlite` WASM/Worker，需要 COOP/COEP；独立静态站还需要在构建时注入 API URL，并在 API 侧配置对应 CORS Origin。Render 免费 Web Service 不支持独立 pre-deploy command，免费实例还会休眠。

## 决策

作品集首版发布使用多阶段 `Dockerfile.production`：

1. Node 阶段执行 `expo export --platform web`；
2. Python 阶段复制 `dist`，FastAPI 在 API 路由之后提供 SPA fallback；
3. Web 默认使用当前 Origin 调用 API；
4. 容器启动前依次执行生产预检、Alembic 和演示数据重置；
5. Render Blueprint 只创建一个 Web Service、PostgreSQL 和 Key Value。

## 结果

优点：

- 消除 API URL/CORS 的部署循环；
- 安全头、404 和 SPA fallback 可由 Pytest 与公网脚本验证；
- 少一个免费计算实例；
- 一个镜像即可复现前后端版本。

代价：

- 静态资源不使用独立 CDN；
- 前后端发布耦合；
- 免费实例冷启动同时影响页面和 API；
- 启动期迁移不是付费平台独立 release phase，Schema 必须向后兼容。

## 被拒绝的方案

- 独立 Render Static Site：可配置安全头，但要处理构建期 API URL、CORS 和两阶段创建；
- Railway 全栈：长期更稳定，但作品集首发通常至少需要 5 美元/月预算；
- Fly.io：控制力强，但当前阶段增加了不必要的资源和数据库运维复杂度。

## 后续触发拆分的条件

- 需要 CDN 缓存和独立前端发布；
- API 冷启动不能影响页面；
- 有稳定付费预算并需要独立 pre-deploy migration；
- 已有真实流量指标证明拆分收益。
