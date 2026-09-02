# 生产网关、可信代理与部署预检

## 1. 为什么应用不能直接相信代理 Header

公网 HTTPS 通常在负载均衡器、Ingress 或托管平台网关终止，API 看到的 TCP 对端往往是代理。客户端可以自行发送 `X-Forwarded-For`；如果应用直接取最左侧值，攻击者只要更换 Header 就能绕过 IP 限流。反过来，如果完全忽略 Header，所有访问者又会共享一个代理地址并互相误伤。

NutriPilot 采用显式信任链：

1. Uvicorn 使用 `--no-proxy-headers`，保留 TCP 对端，不在应用校验前改写 `scope.client`。
2. 只有 TCP 对端位于 `NUTRIPILOT_TRUSTED_PROXY_CIDRS` 时才解析 `X-Forwarded-For`。
3. 地址链从右向左剥离可信代理，遇到第一个不可信地址即视为客户端。
4. 非 ASCII、非法 IP、空元素或超过 20 跳的 Header 退回 TCP 对端。
5. `0.0.0.0/0` 和 `::/0` 被配置模型拒绝，避免“所有客户端都是可信代理”。

例如：

```text
X-Forwarded-For: 攻击者伪造值, 真实客户端, 内层代理
TCP peer: 最后一层可信代理

右向左：
最后一层代理（可信）→ 内层代理（可信）→ 真实客户端（首个不可信，停止）
```

这要求部署平台提供实际代理网段。网段配置错误时，安全退化方向是忽略 Header 并把流量聚合到 TCP 对端，可能误限流，但不会接受任意伪造地址。

## 2. 账号桶与访客桶

每个登录或注册请求先进入访客总量桶，再进入账号标识桶：

```text
Request
  → trusted client address
  → HMAC("auth-visitor-rate:v1:" + address)
  → visitor fixed window
  → HMAC("auth-rate:v1:" + action + normalized_email)
  → account fixed window
  → password/database work
```

访客桶在登录和注册之间共享，阻止同一来源轮换邮箱绕过；账号桶区分登录和注册，限制多个来源集中攻击一个账号。成功登录只清账号登录桶，不清访客桶，否则攻击者掌握任意一个有效账号后就能不断重置网络预算。

邮箱和 IP 都不会直接进入 Redis。两个键使用独立的 `NUTRIPILOT_RATE_LIMIT_HMAC_SECRET` 做 HMAC-SHA256；该 Secret 与 JWT 签名、AI 凭证加密职责分离，轮换 JWT 不会让限流键突然失联。生产配置拒绝开发默认值。

IP 只能作为滥用信号，不是用户身份。校园网、公司网、运营商 CGNAT 和 IPv6 前缀都可能让多人共享或频繁改变地址，因此阈值必须与账号桶叠加，不能仅凭 IP 永久封禁。

## 3. Host、CORS 与 HTTPS 边界

- `NUTRIPILOT_ALLOWED_HOSTS` 由 `TrustedHostMiddleware` 强制执行；生产环境禁止空列表和通配 `*`。
- CORS 只控制浏览器跨源读取权限，不是服务端鉴权。作品集预检要求显式 HTTPS Web Origin。
- API 容器不自行管理证书。HTTPS、TLS 版本、HSTS、HTTP 到 HTTPS 跳转和边缘 DDoS 缓解应由托管网关负责。
- 应用当前刻意不让 Uvicorn自动采信代理 Header。选择托管平台后，需要用平台文档确认代理网段和 Header 重写规则，再填写 CIDR。

## 4. 非 root 容器

Docker 镜像在复制依赖与应用后创建 `nutripilot` 系统用户，运行期 UID/GID 均非 0。Alembic 和 Uvicorn只需读取镜像文件并连接外部服务，不需要 root。

这会降低容器进程被利用后的权限，但不是完整沙箱。生产平台还应考虑只读根文件系统、能力删除、镜像扫描、资源限制和网络策略。CI 会构建镜像并断言运行 UID 不为 0。

## 5. 生产配置预检

模板位于 `backend/.env.production.example`。真实 Secret 必须由部署平台注入，不能写入 Git。

在部署环境执行：

```powershell
python -m app.cli.production_preflight --portfolio --behind-proxy
```

静态预检会验证：

- `environment=production` 及三个独立生产 Secret。
- PostgreSQL/Redis URL 使用正确 Scheme 且不是 Loopback。
- 认证与 Demo 保护为 fail-closed。
- 作品集关闭公开注册并提供 HTTPS Web Origin。
- Host 白名单显式配置。
- 声明位于代理后时，可信代理 CIDR 非空。

命令只输出检查名和错误，不回显 URL 密码或 Secret，也不替代 `/ready` 的真实依赖连通性检查。生产发布顺序建议为：

```text
配置静态预检
  → 构建/扫描镜像
  → 执行 Alembic migration job
  → 发布 API
  → 外部探测 /live 与 /ready
  → 验证 HTTPS、Host、CORS、代理地址和 429
```

## 6. 真实验收结果

Docker + PostgreSQL 17 + Redis 7.4 临时把访客阈值设为 2，并把 Docker 网桥配置为可信代理：

- 同一真实访客使用不同邮箱，并在 Header 左侧放入不同伪造地址，结果为 401、401、429，`Retry-After=60`。
- 更换真实访客地址后返回 401，说明访客桶互相隔离。
- Redis 中出现 2 个访客摘要键、3 个账号摘要键，均不含 IP 或邮箱。
- 恶意 `Host: evil.example` 返回 400。
- API 容器为 `uid=999(nutripilot)`，命令行包含 `--no-proxy-headers`。
- 生产预检模拟配置返回 `status=ok`。

验收后临时键和阈值已清理，开发配置恢复，API healthy、公开注册为 true、演示登录为 200。

## 7. 尚未完成

- 已选择 Render 免费演示拓扑并准备 Blueprint，但尚未创建真实平台资源，因此没有可公开访问的 HTTPS URL。
- 尚未接入 WAF、验证码、设备信誉、IP/网段渐进封禁和边缘 DDoS 防护。
- 代理 CIDR 尚未用真实平台文档验证；Docker 网桥验收只能证明算法和配置链路。
- 真实 Sentry 项目、Redis 告警、429 异常比例告警和外部可用性探测仍待配置。

可信代理链解析、账号与访客双层 Redis 限流、非 root 容器和生产预检共同缩小了攻击面，但这些代码本身不能证明某个实例已完成生产部署，也不能抵御 DDoS。
