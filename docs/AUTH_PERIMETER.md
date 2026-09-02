# 公开入口与认证风控边界

## 1. 解决的问题

演示账号已有独立限流和资源配额，但原注册接口允许任何访客创建普通账号，从而绕过 `is_demo` 保护。登录接口也没有针对单个账号标识的失败尝试限制，公开部署后会暴露凭证爆破入口。

认证入口现在包含以下应用内边界：

- 部署时可关闭公开注册，后端返回 403，客户端通过公开运行配置隐藏注册入口。
- 登录与注册在执行密码哈希、数据库查询或写入前依次进入访客和账号 Redis 原子桶。
- 只有 TCP 对端属于可信代理 CIDR 时才读取 `X-Forwarded-For`。

这些控制是作品集公开部署的最低应用保护，不等于完整 WAF、验证码或 DDoS 防护。

## 2. 请求流程

```text
Expo 登录页
  → GET /api/v1/meta/config
      ├─ registration_enabled=true：显示登录/注册
      └─ false 或配置请求失败：只显示登录

POST /auth/register
  → public_registration_enabled?
      ├─ false：403，不做哈希和数据库写入
      └─ true：HMAC(client address) 访客桶
                → HMAC(email, action=register) 账号桶
                → 注册

POST /auth/login
  → HMAC(client address) 访客桶
  → HMAC(email, action=login) 账号桶
  → 用统一错误验证账号与密码
      ├─ 失败：401，保留计数
      └─ 成功：签发令牌并删除该登录桶
```

前端隐藏入口只改善体验。攻击者可以绕过 UI 直接请求 API，因此真正的注册开关和限流必须在后端执行。

## 3. 隐私化限流键

邮箱由 Pydantic 校验后再按认证服务规则规范化。应用使用独立限流 Secret 对以下带版本、动作域隔离的消息计算 HMAC-SHA256：

```text
auth-rate:v1:{login|register}:{normalized_email}
```

Redis 键只包含动作和 64 位摘要：

```text
nutripilot:auth-rate:login:<64 hex chars>
```

访客地址使用另一个消息域生成 `nutripilot:auth-visitor:<digest>`。这比普通 SHA-256 更适合低熵标识符：拿到 Redis 数据的人不能只靠常见邮箱/IP 字典验证猜测。登录、注册和访客域互相隔离；限流 Secret 与 JWT Secret 分离，JWT 轮换不会让现有桶失联。

## 4. Redis 原子性与故障策略

认证保护和演示保护共用 `RedisRateLimiter`。Lua 在一次执行中完成：

1. `INCR` 计数。
2. 第一次命中时设置 `PEXPIRE`。
3. 读取 `PTTL`，用于生成 `Retry-After`。

生产环境若启用认证保护，配置校验强制 `auth_protection_fail_closed=true`。Redis 故障时登录和注册返回 503，但已经持有 Refresh Token 的用户仍可刷新会话，普通鉴权业务也不依赖认证桶。开发环境默认 fail-open，便于只启动最小依赖调试。

成功登录会清除该账号标识的登录桶，避免正常用户被自己的历史输错长期占用额度；失败和未知邮箱都会保留计数，并使用相同 401 文案。认证服务对不存在的账号仍验证固定 Argon2 假哈希，缩小显式错误和主要计算路径的账号枚举差异。注册冲突同样消耗注册桶，因为它仍产生数据库与响应成本。

登录服务会先在 PostgreSQL 提交 Refresh Token，再清理短期 Redis 桶。入口检查必须 fail-closed；但如果 Redis 恰好在成功后的清理阶段故障，清理只记录告警，不把已经提交的成功登录改成 503，否则会留下客户端拿不到的有效 Refresh Token。

## 5. 配置

```dotenv
NUTRIPILOT_PUBLIC_REGISTRATION_ENABLED=false
NUTRIPILOT_AUTH_PROTECTION_ENABLED=true
NUTRIPILOT_AUTH_PROTECTION_FAIL_CLOSED=true
NUTRIPILOT_AUTH_RATE_LIMIT_WINDOW_SECONDS=900
NUTRIPILOT_AUTH_LOGIN_ATTEMPTS_PER_WINDOW=10
NUTRIPILOT_AUTH_REGISTER_ATTEMPTS_PER_WINDOW=5
NUTRIPILOT_AUTH_VISITOR_REQUESTS_PER_WINDOW=30
NUTRIPILOT_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"]
NUTRIPILOT_RATE_LIMIT_HMAC_SECRET=<独立高熵部署Secret>
```

本地开发默认允许注册、15 分钟内每个邮箱 10 次登录尝试、5 次注册尝试、每个访客 30 次认证尝试。公开作品集环境建议关闭注册，只提供可重置演示账号。代理算法与部署边界见 [`PRODUCTION_GATEWAY.md`](PRODUCTION_GATEWAY.md)。

## 6. 已验证行为

- 单元测试验证邮箱大小写规范化、动作隔离、HMAC 键不含邮箱、429/`Retry-After`、成功清桶和 Redis fail-open/fail-closed。
- API 集成测试验证运行配置、后端关闭注册、登录/注册路由接入保护，以及只有成功登录才清桶。
- Docker + PostgreSQL 17 + Redis 7.4 验收中，关闭注册返回 403；阈值设为 2 后，同一未知邮箱得到 401、401、429，`Retry-After` 为 60。
- Redis 实际键只有动作和 64 位摘要。演示账号先输错一次、成功登录、再输错时重新得到 401、401、429，证明成功清桶。
- Expo Web 浏览器验收中，关闭注册时精确“注册”入口数量为 0、关闭提示为 1；恢复配置并刷新后入口数量恢复为 1。
- 可信代理验收中，同一访客轮换邮箱和左侧伪造地址仍得到 401、401、429；另一个访客为 401，Redis 键不含 IP。

验收后已删除临时认证键并恢复默认开发配置，API 健康且演示账号登录返回 200。

## 7. 明确未解决的边界

- 账号与访客桶仍不能阻止轮换大量 IP/邮箱的分布式低频攻击。
- 可信代理 CIDR 必须按真实托管平台配置；配置为空会聚合到 TCP 对端，配置过宽会产生伪造风险。
- 尚未接入验证码、设备信誉、WAF、网关全局速率或异常告警。
- 固定假哈希只能缩小主要计算路径差异，不能证明网络层完全不存在可统计的时序侧信道。
- 公开运行配置只暴露是否允许注册，不返回密钥、阈值或内部环境信息。

这些控制共同降低认证接口的滥用风险，但不能等同于阻止所有暴力破解，也不能替代企业级 WAF、验证码和平台级流量清洗。
