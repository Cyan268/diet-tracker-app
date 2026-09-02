# U1：独立 VPS 生产包

本目录不修改现有 Render 服务，也不使用根目录的开发 `compose.yaml`。U1-01 生产包与 U1-02 发布/迁移/应用回滚均已完成本地验收；服务器 HTTPS、异地备份恢复和首次公网验收属于 U1-03。实际结果见 [U1-01](../docs/upgrade/tasks/U1-01.md)、[U1-02](../docs/upgrade/tasks/U1-02.md)和独立的[发布手册](RELEASE.md)。

## 1. 运行边界

```text
80/443 → Caddy (.2) → API + Expo Web (.3):8000
          edge 网络         │
                       data 内部网络
                         PG / Redis
```

- 只有 Caddy 发布业务端口。PG、Redis、API 和 Caddy 管理端口 2019 均不发布。
- edge 连接 Caddy/API 并提供出网；data 为 internal，仅 API、维护容器、PG、Redis 加入。代理不能访问 data 网络。
- API 固定信任代理 IPv4 `/32`；Caddy 用实际 TCP 对端重建 X-Forwarded-For。Uvicorn 不采信代理头。此配置不支持直接加 CDN/LB；增加一跳须重新验证。
- 预留独立 Worker 的同镜像契约，但没有启用空壳服务。U3-01 实现入口、租约和健康检查后再添加 Worker 及受限出网。
- `maintenance` 在 ops profile 中，只执行显式命令；不随默认 up 启动，也没有固定 edge IP，不会与运行中的 API 抢地址。
- 单服务器仍是单点，不是高可用。API 单进程，资源限制是初始保护值，不是容量测量结果。

API 镜像使用非 root 用户、只读根文件系统及临时 `/tmp`，不挂载宿主 Docker socket。所有服务的 Docker JSON 日志按 10MB × 3 个文件轮换。Caddy 不启用访问日志，运行错误日志删除 request/response headers 字段；API 禁用 Uvicorn 访问日志，沿用应用脱敏日志。不要启用 SQL echo 或把带正文的原始日志上传。

## 2. 构建与版本

在本机/CI 构建，不在小 VPS 上安装 Node 或进行构建：

```sh
docker build -f Dockerfile.production --target vps \
  --build-arg BUILD_REVISION=YOUR_FULL_GIT_SHA \
  --build-arg SOURCE_REVISION=YOUR_FULL_GIT_SHA \
  -t your-registry/nutripilot:YOUR_FULL_GIT_SHA .
```

必须指定 `--target vps`。Dockerfile 的默认最后阶段仍为 render，保留旧 Render 启动契约。VPS Compose 再明确指定 `app.cli.serve_vps`，启动只做静态预检、设置 Schema 就绪要求和启动一个 API 进程，不迁移、不种子、不自动重置。

Dockerfile 支持 NODE_IMAGE/PYTHON_IMAGE 构建参数以固定官方 digest。U1-02 已由 CI/人工发布 workflow 生成全部镜像的 digest manifest、扫描报告和 current/previous 回滚集合；生产执行禁止只写 latest。Compose 中的 PG/Redis tag 只是默认模板，实际 release env 必须与 manifest 的 digest reference 完全一致。

## 3. 配置与密钥

复制 [env.production.example](env.production.example) 为 Git 之外的受限配置文件，填写镜像版本、域名、代理/API 地址和密钥目录。不要 source 配置文件执行内容；脚本只交给 Compose 解析。

推荐 Linux 宿主目录 `/etc/nutripilot/secrets`：父目录 root 所有、0700；每个下列文件仅存对应值，没有 `KEY=` 前缀，没有引号。文件可设为 0444，依靠宿主父目录限制读取，并使非 root API 在绑定挂载后可读。Compose 本地 file secrets 并非加密保险库；其 uid/gid/mode 重映射支持有边界，不能只写 YAML mode 就认为宿主权限已生效。部署时检查实际挂载和读取权限，root/Docker 管理员仍能读取这些值。[Docker Secrets 文档](https://docs.docker.com/compose/how-tos/use-secrets/)

| 文件名                               | 值与用途                                                                           |
| ------------------------------------ | ---------------------------------------------------------------------------------- |
| postgres_password                    | 独立高熵 PG 密码                                                                   |
| nutripilot_database_url              | postgresql+psycopg URL，用户/库为 nutripilot，主机 postgres；密码部分正确 URL 编码 |
| nutripilot_jwt_secret                | 独立随机签名密钥，至少 32 字符                                                     |
| nutripilot_credential_encryption_key | 独立加密密钥，至少 32 字符；需与数据库备份分开保管                                 |
| nutripilot_rate_limit_hmac_secret    | 独立随机 HMAC 密钥，至少 32 字符                                                   |
| nutripilot_demo_reset_password       | 专用演示密码，至少 10 字符；初始化/明确重置时使用                                  |

PG 密码和 URL 中的密码必须一致。不要重用三个应用密钥。轮换凭证加密密钥会影响历史凭证解密，不能直接换掉后称升级成功。容器内通过 `NUTRIPILOT_SECRETS_DIR=/run/secrets` 加载；兼容已有环境变量优先级，但拓扑预检拒绝把这些敏感字段直接放入 API environment。真实配置、密钥目录、测试凭证都在 Git 与构建上下文之外。

Redis 只在内部数据网络可访问，本版本未配置 Redis 密码/TLS；保护边界是宿主权限和容器网络，不适合共享不可信租户。使用 AOF、96MB noeviction；内存耗尽/停机时保护接口失败关闭，不通过缓存驱逐悄悄解除限流。Redis 状态不是业务数据备份。

公开注册默认关闭、规则 Provider 默认启用、自动 Demo 重置间隔固定为 0。未配置或调用真实模型。公开演示账号不得保存私人资料。

## 4. 显式执行次序

下面的低层命令保留用于理解和故障诊断，不是推荐的正式发布入口，也不是授权自动操作生产。正常发布应按 [RELEASE.md](RELEASE.md) 使用控制器，确保互斥、备份、状态提升和回滚约束不会被跳过。首次生产执行前必须确认服务器、域名、权限、旧数据和备份安排。本地测试也要使用独立项目名/卷，禁止与已有业务数据混用。

```sh
# 在仓库根；例子中的路径由管理员确认，不包含真实 Secret 值。
bash scripts/deploy/preflight.sh /etc/nutripilot/config.env
docker compose --env-file /etc/nutripilot/config.env -f deploy/compose.prod.yml up -d postgres redis

# 维护窗口内显式升级。不得有旧版日志写入器同时运行。
docker compose --env-file /etc/nutripilot/config.env -f deploy/compose.prod.yml run --rm maintenance alembic upgrade head
docker compose --env-file /etc/nutripilot/config.env -f deploy/compose.prod.yml run --rm maintenance alembic check

# 仅首次需要演示账号时执行；存在同名账号会拒绝，不自动覆盖。
docker compose --env-file /etc/nutripilot/config.env -f deploy/compose.prod.yml run --rm maintenance python -m app.cli.seed_demo --allow-production

docker compose --env-file /etc/nutripilot/config.env -f deploy/compose.prod.yml up -d api proxy
bash scripts/deploy/smoke-readonly.sh https://YOUR_HOST
```

预检验证拓扑/配置/挂载读取/Caddy 语法，不验证数据库可达，也不会启动依赖、迁移或初始化；一次性检查可能创建 Compose 网络。API readiness 检查数据库和镜像要求的 Alembic head；缺迁移返回 503。Redis 健康由其独立容器探针及认证失败关闭行为观察，不能用 API readiness=200 表示全部依赖正常。Worker 健康未来单独增加。

迁移失败必须停在失败处，不继续“更新服务”。U1-02 控制器已经实现发布互斥、必要时生成并验证本机备份、失败停止和兼容应用回滚；仍没有生产 restore 或异地上传，恢复验收属于 U1-03。手工执行本节命令不会自动获得控制器保证。

需要清空共享演示账号时另行明确执行 `python -m app.cli.reset_demo --allow-production`；它会轮换账号身份、使旧 Token 失效。它不是普通重启步骤。禁止对真实用户数据执行 Demo 重置。

## 5. 隔离本地检查（Windows 也可用）

```powershell
node scripts/deploy/init-local-test.mjs
# 再次运行拒绝覆盖已有测试密钥；无需反复初始化。
docker build -f Dockerfile.production --target vps -t nutripilot:vps-u1-local .
docker compose --env-file deploy/.local/u1-01/config.env -f deploy/compose.prod.yml --profile ops config --format json | backend/.venv/Scripts/python.exe -m app.cli.vps_topology --local
docker compose --env-file deploy/.local/u1-01/config.env -f deploy/compose.prod.yml up -d postgres redis
docker compose --env-file deploy/.local/u1-01/config.env -f deploy/compose.prod.yml run --rm maintenance alembic upgrade head
docker compose --env-file deploy/.local/u1-01/config.env -f deploy/compose.prod.yml run --rm maintenance python -m app.cli.seed_demo --allow-production
docker compose --env-file deploy/.local/u1-01/config.env -f deploy/compose.prod.yml up -d api proxy
```

Windows 上不要直接假设 `bash` 是 Git Bash：本机 `C:\Windows\System32\bash.exe` 通常进入 WSL，若未开启 Docker Desktop 的 WSL integration，脚本内会找不到 Docker。可以使用已安装的 Git Bash：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' scripts/deploy/preflight.sh deploy/.local/u1-01/config.env --local
& 'C:\Program Files\Git\bin\bash.exe' scripts/deploy/smoke-readonly.sh http://localhost:8086
```

预检脚本已经处理 Git Bash 对 `/etc/caddy/Caddyfile` 的路径改写；代理运行时改为在现有容器内 validate，避免一次性容器争抢固定 IP。

配置仅绑定 loopback 8086/8446；本地入口为 `http://localhost:8086`（浏览器安全上下文例外），不证明公网 HTTPS/TLS 验收完成。测试账号为 `demo@nutripilot.example`，密码 `U1-Local-Demo-Only-2026!`，只用于此独立 fixture，严禁用于公网。真实随机密钥保留在被忽略的 `deploy/.local/u1-01`，脚本不打印它们。

在 backend 执行 `python scripts/check_vps_local.py --phase http` 或 `--phase business`：前者验证 HTTP/SPA/WASM/安全头/鉴权门禁/请求体上限，后者只对本地测试账号写入合成记录，验证重放、乐观锁及同步墓碑并退出。`spoof` 和依赖停机 phase 是故障实验辅助，需在单独测试网络/受控停机窗口执行；不可针对生产运行。

停止本地服务用明确项目配置的 `docker compose ... stop`；不自动删除卷。测试卷与 Secret 文件保留便于复测，确认无保留价值后再单独清理。不要执行开发目录的 `down -v` 以免删错项目数据。

## 6. 代理与浏览器检查

Caddy 对请求体限制 1MB（当前文本 API 的工程上限，不是营养学或未来图片上限）。U3 图片直传需单独校验/签名/CORS，而不是随意放大所有端点。Caddy 默认 HTTPS 由真实域名触发；正式发布需确认 DNS、80/443、证书与续期。没有配置 UDP/HTTP3 端口，不宣称已启用 HTTP3。[请求体限制](https://caddyserver.com/docs/caddyfile/directives/request_body)、[自动 HTTPS](https://caddyserver.com/docs/automatic-https)

COOP same-origin、COEP credentialless、nosniff 保留；WASM MIME 由同源 FastAPI 静态文件响应提供。跨域图片测试目前只验证浏览器隔离兼容性，不等同于已实现私有对象存储或签名上传。对象存储选择/费用/地域仍待 U3 与用户确认。

检查项目至少包括：非法 Host 不路由至 API、CORS 无越权许可、伪造多个 X-Forwarded-For 仍触发同一访客限流桶、不同真实容器来源不被合成一个桶、数据库/Redis/API 无宿主端口、API 连续重启不改账号/日志/Schema。HTTP 冒烟、浏览器 Web SQLite 和真实 HTTPS 是三个不同证据层级。

正式公网发布仍需要 U1-03 的 required reviewer 仓库设置确认、服务器执行、异地备份恢复、HTTPS 和容量证据；本目录和 U1-02 工作流存在不意味着服务器已上线。

## U1-03 本机备份与隔离恢复

`database_recovery.py` 在活动发布锁内生成 PostgreSQL custom-format dump，先用
`pg_restore --list` 解析，再记录 SHA-256、不可变 PostgreSQL 镜像以及核心业务表行数。
默认只保留最近 7 份本机备份。`deploy/systemd` 中的 timer 每天触发一次，安装后仍需
通过 `systemctl list-timers` 和一次手工运行验收，不能只因文件存在就声称已启用。

```sh
python3 scripts/deploy/database_recovery.py backup \
  --env-file /etc/nutripilot/releases/current.env \
  --state-dir /var/lib/nutripilot/release-state \
  --backup-dir /var/lib/nutripilot/backups \
  --keep 7

python3 scripts/deploy/database_recovery.py restore-drill \
  --receipt /var/lib/nutripilot/backups/<backup>.receipt.json
```

恢复演练没有“目标数据库”参数：工具只会创建无网络、无映射端口、tmpfs 存储的临时
PostgreSQL 容器，恢复后比较 Schema 与核心表行数，并在成功或失败时删除容器。它不会
覆盖生产库。当前用户明确不采用异地对象存储，因此这些备份只能抵抗应用误操作，不能
抵抗服务器或系统盘整体丢失；不得把它描述为完整灾难恢复。
