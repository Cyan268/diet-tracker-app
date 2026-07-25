# 后端可观测性与错误监控

## 1. 目标

生产问题不能只靠“在本机复现”。这一层需要回答四个问题：

1. 哪个请求失败了？
2. 失败发生在哪个端点、耗时多久、返回什么状态？
3. 用户如何把页面错误与服务端日志关联起来？
4. 在不记录 API Key、饮食正文和认证信息的前提下，如何获得异常堆栈？

当前实现包括 JSON 结构化日志、`X-Request-ID` 请求追踪、统一 500 响应、可选 Sentry 错误与性能监控，以及对应的脱敏回归测试。Sentry DSN 默认不配置，因此本地开发不会向第三方发送数据。

## 2. 请求追踪链路

```text
客户端 X-Request-ID（可选）
  → 只接受 8~128 位字母、数字、点、下划线和连字符
  → 非法或缺失时生成 32 位随机 ID
  → ContextVar 绑定当前异步请求
  → JSON 请求完成日志
  → 响应头 X-Request-ID
  → 未处理异常响应体 + Sentry tag
```

客户端提供的 ID 必须校验，避免换行符制造伪造日志。`request_id` 用于一次 HTTP 请求的关联；AI 响应中的 `trace_id` 指向数据库中的一次 AI 调用记录，两者职责不同，不能混为一个字段。

## 3. JSON 日志契约

示例：

```json
{
  "timestamp": "2026-07-22T05:03:39.637+00:00",
  "level": "INFO",
  "logger": "nutripilot.http",
  "event": "request.completed",
  "request_id": "docker-final-20260722",
  "environment": "development",
  "method": "GET",
  "endpoint": "app.api.routes.health.readiness",
  "status_code": 200,
  "duration_ms": 2
}
```

Formatter 只输出固定白名单字段，不会遍历任意 `LogRecord.extra`。请求日志使用低基数的端点函数标识，不保存原始 URL、路径参数、Query、请求正文、Header、Cookie、IP 或用户 ID。Uvicorn 默认 access log 会包含原始 Query，因此应用启动时显式关闭它，由结构化请求日志替代。

状态码对应级别：2xx/3xx 为 `INFO`，4xx 为 `WARNING`，5xx 为 `ERROR`。未处理异常只记录异常类型，不把异常消息直接写入控制台日志，因为下游异常文本可能意外包含数据库值或用户输入。

## 4. Sentry 配置与隐私边界

Sentry 官方 FastAPI 集成在初始化 Python SDK 后自动启用，并默认捕获导致 500 的异常；官方文档也说明请求 URL、Header 和 JSON 等可能附加到事件中，因此本项目额外采用更严格的配置：[Sentry FastAPI 集成](https://docs.sentry.io/platforms/python/integrations/fastapi/)。

```env
NUTRIPILOT_SENTRY_DSN=https://public-key@host/project-id
NUTRIPILOT_SENTRY_TRACES_SAMPLE_RATE=0.05
NUTRIPILOT_RELEASE=nutripilot-api@commit-sha
```

保护措施：

- `send_default_pii=false`
- `include_local_variables=false`
- `max_request_body_size=never`
- `before_send` 删除 user、URL、Header、Cookie、Query、Body 和 WSGI/ASGI 环境
- 只给异常添加已校验的 `request_id` 标签
- DSN 未设置时 SDK 不初始化

Sentry 官方配置说明确认 `before_send` 可以在发送前修改或丢弃事件，且 `max_request_body_size=never` 可禁止请求正文采集：[Sentry Python SDK Options](https://docs.sentry.io/platforms/python/configuration/options/)。关闭 PII 不代表绝对不会泄露敏感信息，新的集成和自定义上下文仍必须经过代码审查与测试。

## 5. 告警建议与未完成边界

代码侧已具备 Sentry 接入能力，但当前没有真实生产 DSN，因此不能声称“线上告警已验证”。部署后建议配置：

- 新出现的 5xx Issue：立即通知。
- 5 分钟内错误率明显上升：高优先级告警。
- API P95 延迟连续超过基线：性能告警。
- AI 降级率或失败率升高：基于 `ai_call_logs` 的业务告警。
- 健康检查失败：由部署平台从应用外部探测，而不是依赖同一进程自报。

告警阈值需要基于真实流量调整，否则过低会产生告警疲劳，过高又会漏报。下一步是在真实部署环境创建 Sentry 项目、设置 Release/Source Map、告警路由和一次受控异常验收。

## 6. 验证结果

- 单元测试覆盖 ID 复用、非法字符、端点低基数、响应头、500 响应和 Sentry 关联标签。
- 隐私测试验证 Authorization、API Key、Query、Cookie、Body、用户和异常文本不进入结构化日志或 Sentry 事件。
- Docker/PostgreSQL 环境中 `/health/ready` 返回 200 和相同 `X-Request-ID`。
- 容器日志为单行 JSON，包含端点、状态和耗时，不包含测试 Query `token=must-not-log`。
