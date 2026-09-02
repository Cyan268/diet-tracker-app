# NutriPilot 发布、迁移与应用回滚手册

本手册描述可复现的发布控制面。公网主机初始化、备份恢复、DNS/HTTPS、防火墙和容量验收仍需由部署者在受控维护窗口中完成。

## 1. 发布不变量

- 生产 `release` 与 `sourceRevision` 必须是同一个完整 40 位 Git SHA；应用和三个基础组件必须使用 `@sha256:` 引用，拒绝 `latest`。
- Compose 解析后的 API、maintenance、Caddy、PostgreSQL、Redis 镜像必须逐项等于 manifest；敏感值只能通过 file secrets 挂载。
- 同一状态目录只能有一个发布持有 `.release.lock`。锁内记录 PID、主机和时间；不能在进程仍运行时手工删除。
- 顺序固定为：解析/预检 → 获取并核对镜像 → 启动数据依赖 → 必要备份及验证 → 读取 Schema → 停止旧写入器 → `upgrade head`/`check` → 核对目标 Schema → 启动 API/Caddy → ready/HTTP 冒烟 → 原子提升 manifest。
- 迁移或验证失败后不启动候选应用、不更新 `current.json`。首版允许短暂维护窗口，不承诺零停机。
- 回滚只切应用/组件镜像。旧 manifest 必须声明兼容当前数据库；工具永不执行 `alembic downgrade`。

## 2. CI 与发布构件

普通 push/PR 的 [CI](../.github/workflows/ci.yml)会：

1. 在真实 PostgreSQL 服务上执行 Alembic 和后端测试，保留原覆盖率门禁。
2. 以 `${GITHUB_SHA}` 构建明确的 `vps` target，并核对 OCI revision/release 标签。
3. 用 Trivy 记录 JSON 报告，并在存在已有修复的 HIGH/CRITICAL 漏洞时失败；未修复项仍保留在完整报告中评估。
4. 上传 manifest 与扫描报告为 v4 artifact；PR 不登录生产仓库、不读取生产 Secret、不部署。

[手动发布工作流](../.github/workflows/publish-vps-image.yml)只接受完整 SHA，验证它属于默认分支历史，要求显式布尔确认，使用并发组防止重复发布，并绑定 `production-release` environment。仓库管理员仍必须在 GitHub Settings → Environments 中为该 environment 配置 required reviewers/允许分支；仅在 YAML 中写 environment 名称并不自动产生审核人。

人工批准后，工作流先扫描本地镜像，再用 GitHub 内置短期 Token 推送 SHA tag，最后从本地 RepoDigests 生成生产 manifest。artifact 是发布输入，不应在服务器上重新构建镜像或手改 JSON。

## 3. 生产前准备

管理员需要保留三个互相独立的目录：

```text
/etc/nutripilot/releases/<git-sha>.env       # 每个版本的非密钥 Compose 参数
/etc/nutripilot/secrets/*                    # 受限 file secrets
/var/lib/nutripilot/release-state/           # current/previous/lock/本机备份
```

从 CI 下载 `release-manifest.json`，把 manifest 中的五个 `reference` 原样写入相应 release env；`NUTRIPILOT_RELEASE` 写完整 Git SHA。不要只复制 SHA tag，生产 Compose 必须使用 digest。状态目录和 release env 应仅由部署管理员写入。

首次上线前必须确认服务器、域名、旧数据去留和备份方案。当前自动备份只验证本机 `.dump` 可被 `pg_restore --list` 读取并绑定 SHA-256；同盘备份不能抵抗磁盘或主机丢失，也不等于执行过恢复。

## 4. 执行发布

在与 manifest 相同、受信任的 Git SHA checkout 中执行；下面路径必须由管理员确认：

```sh
python scripts/deploy/release_controller.py apply \
  --candidate /etc/nutripilot/releases/<git-sha>.manifest.json \
  --env-file /etc/nutripilot/releases/<git-sha>.env \
  --state-dir /var/lib/nutripilot/release-state \
  --smoke-url https://YOUR_HOST
```

若 manifest 的 `requiresBackup=true`，控制器会在锁内、迁移前生成 custom-format dump，调用 `pg_restore --list` 校验，并将带 release/source/hash/size 的收据放入 `state/backups`。也可传入 `--backup-receipt`，但收据和文件必须存在、哈希一致且绑定本次 release。

发布成功后：

- 原 `current.json` 原子移动为 `previous.json`；候选写为 `current.json`。
- 两者只保存镜像/Schema/时间与 env 文件哈希，不复制 Secret。
- 首次发布没有 `previous.json`，因此没有可用的应用回滚目标。

## 5. 应用回滚

先准备与 `previous.json` 完全匹配的上一版 env，然后执行：

```sh
python scripts/deploy/release_controller.py rollback \
  --env-file /etc/nutripilot/releases/<previous-git-sha>.env \
  --state-dir /var/lib/nutripilot/release-state \
  --smoke-url https://YOUR_HOST
```

工具先启动/确认 PG 与 Redis，读取当前 Alembic revision；只有该 revision 在旧 manifest 的 `compatible` 中才停止现应用。成功后 current/previous 互换，数据库不变。若不兼容，命令在改变 API/Caddy 之前失败，管理员必须前滚修复或按独立恢复方案处理，不能猜测执行 downgrade。

## 6. Expand/Contract 与不可逆变化

一个旧应用要能在新 Schema 上回滚，迁移必须先扩展、后收缩：

1. expand：新增 nullable 列/新表/新索引，旧代码仍能运行；
2. migrate：部署能同时读旧/新结构的代码，回填并观察；
3. contract：确认所有实例和回滚窗口结束后，再在独立发布删除旧结构。

删除列/表、不可逆数据重写、缩窄类型和更换凭证加密密钥不能靠应用回滚恢复。它们需要单独窗口、已验证恢复、前滚脚本和人工决策；manifest 的兼容列表应拒绝旧镜像，而不是为了让回滚按钮可点而虚报兼容。

## 7. 本地复现

本地发布 fixture 使用独立项目 `nutripilot-release-test`、loopback 8087/8447 和独立卷：

```powershell
node scripts/deploy/init-local-release-test.mjs
python scripts/deploy/release_controller.py manifest --local <其余参数> --output <manifest>
python scripts/deploy/release_controller.py apply --local --candidate <manifest> --env-file <env> --state-dir deploy/.local/release-test/state --smoke-url http://localhost:8087
python scripts/deploy/release_controller.py rollback --local --env-file <previous-env> --state-dir deploy/.local/release-test/state --smoke-url http://localhost:8087
```

`--local` 只放宽 Git SHA/digest 约束，仍校验镜像 ID、Compose 对齐、互斥、Schema、ready 与安全头。
