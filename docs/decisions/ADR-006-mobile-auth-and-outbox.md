# ADR-006：移动端凭证、账号隔离与 Outbox 同步

- 状态：已接受
- 日期：2026-07-15

## 背景

移动端接入账号后需要同时解决三件事：凭证不能明文放入 SQLite；弱网写入不能丢失或重复；用户切换账号后不能看到上一个账号的本地数据。只完成登录页面并不代表客户端已经具备安全、可靠的全栈数据链路。

## 决策

- Access Token 只保存在 JavaScript 内存中，应用重启后通过 Refresh Token 获取新的 Access Token。
- Refresh Token 与最小用户信息作为一个小型会话对象，使用 Expo SecureStore 异步写入；Android 由 Keystore 保护，iOS 使用 Keychain。
- 同一时刻只允许一个刷新 Promise。多个 API 请求同时收到 401 时共享刷新结果，避免旧 Refresh Token 被并发重复使用而触发令牌家族撤销。
- 服务器不可达但存在本地会话时允许进入离线模式；Refresh Token 明确返回 401 时清除本地凭证并要求重新登录。
- OpenAPI JSON 由 FastAPI 应用导出，`openapi-typescript` 生成只包含类型、无运行时开销的 TypeScript 契约；CI 同时检查 OpenAPI 和生成文件是否漂移。
- SQLite v2 为用户资料、饮食记录和 Outbox 增加 `owner_user_id`。旧单机数据由第一个成功登录账号认领，所有查询、统计、导出和同步队列按当前账号过滤。
- 本地饮食写入和 Outbox 事件使用 `withExclusiveTransactionAsync` 在同一事务提交。新增、更新、删除事件会合并，避免无意义的网络请求。
- 同步在登录成功、App 回到前台、每 60 秒和用户手动触发时运行。同一进程内只允许一个同步任务。
- 可重试错误使用最长 5 分钟的指数退避；HTTP 409/422 标记为 `blocked`，不无限重试；启动时回收超过 5 分钟仍为 `processing` 的中断事件。

## 取舍与限制

- SecureStore 适合小型凭证，不是业务数据库，也不应保存大量用户数据。
- Refresh Token 轮换后、写入 SecureStore 前如果进程崩溃，客户端可能丢失新令牌并需要重新登录。严格解决需要服务端提供短暂重试宽限或设备会话协议，不能用“把旧令牌继续存着”掩盖。
- 当前 Outbox 已支持本地到云端的推送；从云端拉取其他设备新增记录、冲突合并界面和后台系统任务仍未完成。
- Expo SQLite 的独占事务不支持 Web；当前可靠同步目标是 Android/iOS，Web 端需要单独的事务适配策略。
- 安全审计在非破坏性修复后仍有 Expo SDK 54 依赖树中的中危公告；修复建议要求跨主版本升级到 Expo 57，因此不使用 `--force`。后续按完整 SDK 升级流程处理。

## 参考

- Expo SecureStore SDK 54：<https://docs.expo.dev/versions/v54.0.0/sdk/securestore/>
- Expo SQLite SDK 54：<https://docs.expo.dev/versions/v54.0.0/sdk/sqlite/>
- OpenAPI TypeScript CLI：<https://openapi-ts.dev/cli>
