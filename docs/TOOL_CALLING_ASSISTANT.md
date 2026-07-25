# 可追溯 Tool Calling 饮食助手

## 1. 本阶段解决什么问题

普通聊天模型不知道用户真实吃了什么。如果直接把问题交给模型，模型可能用常识补全、混入其他用户数据，或把“没有记录”误写成“没有进食”。助手被限制为一个多轮、只读、可追溯的数据问答入口：模型只能通过后端定义的工具读取当前用户数据，回答页面同时展示实际调用依据。

当前支持三个工具：

| 工具                | 用途                                       | 数据边界                                   |
| ------------------- | ------------------------------------------ | ------------------------------------------ |
| `get_today_summary` | 查询指定日期的营养汇总、个性化目标与剩余量 | 仅当前用户饮食记录和资料                   |
| `get_weekly_trend`  | 查询截至指定日期的固定七天趋势             | 仅当前用户；缺失日期补零并单独报告记录天数 |
| `search_food`       | 搜索营养参考食品                           | 公共食品和当前用户私有食品                 |

## 2. 端到端流程

```text
用户问题 + reference_date
  → Bearer JWT 解析当前 user_id
  → 选择用户级 OpenAI Key / 服务端 Key / 本地规则助手
  → Responses API 返回 function_call(name, arguments, call_id)
  → 后端校验工具名与严格参数 Schema
  → 服务端注入 user_id 并执行只读 SQL
  → 以相同 call_id 回传 function_call_output
  → 模型基于工具结果生成最终回答
  → API 返回 answer + evidence + trace_id + Token/延迟/降级状态
```

这里最重要的边界是：`user_id` 不在模型可填写的参数 Schema 中，而是由通过鉴权的服务端上下文注入。即使模型构造恶意参数，也不能选择另一个用户。食品可见性继续复用领域仓储的 `public OR owner=user_id` 约束。

## 3. 为什么不是让模型直接查数据库

模型不持有数据库连接，也不能生成或执行任意 SQL。工具层相当于应用服务白名单：每个工具有固定输入、固定返回结构和查询范围，便于权限审计、测试与后续限流。首版工具全部只读，因此助手无法新增、修改或删除饮食记录。

OpenAI 工具定义启用 `strict: true`，对象 Schema 使用 `additionalProperties: false` 并声明所有字段；服务端仍使用 Pydantic 再校验一次。严格 Schema 只保证参数形状，不保证业务权限，所以鉴权和用户隔离必须留在确定性代码中。

## 4. Tool Calling 循环与失控保护

首轮使用 `tool_choice: "required"`，避免模型在没有真实数据时直接回答；拿到工具结果后的轮次改为 `auto`，允许模型结束回答。`parallel_tool_calls: false` 将每轮限制为零或一次工具调用，首版最多执行三轮工具，超过上限立即报错并进入既有降级策略。请求设置 `store: false`，不依赖供应商保存对话状态。

函数调用不是一次普通 HTTP 响应：模型先返回 `function_call`，应用执行工具，再把带相同 `call_id` 的 `function_call_output` 加入下一次请求。若漏传原始输出项或 `call_id` 对不上，模型无法把结果关联回调用。

实现遵循 OpenAI 官方的 [Function calling 指南](https://developers.openai.com/api/docs/guides/function-calling) 与 [Conversation state 指南](https://developers.openai.com/api/docs/guides/conversation-state)。

## 5. 可靠性、隐私与可解释性

- 用户未配置 Key 时使用确定性的本地只读助手；无效凭证、限流或模型故障时也可降级，并向用户解释原因。
- 回答必须至少带一条工具证据；界面展示工具名称、摘要、Provider、模型、Prompt 版本、延迟、Token 和追踪 ID。
- AI 调用日志只保存问题的 SHA-256 指纹，不保存原始问题；哈希用于排查重复调用，不应宣称匿名化。
- “0 kcal”只表示该日期没有被系统记录，不能推断用户没有进食。周趋势同时报告 `days_with_records/7`，防止把不完整记录当完整数据。
- 所有回答带非医疗免责声明。助手不诊断疾病、不调整药物，也不取代医生或注册营养师。

## 6. 已验证内容

- HTTP Mock 验证两轮 Responses Tool Calling、严格 Schema、`call_id` 关联、Token 汇总和模型标识。
- 双用户 API 测试验证每日汇总和私有食品不越权。
- 固定七天窗口测试验证日期、记录天数和总热量，并确认零热量记录仍算已记录日期。
- 无效用户 Key 测试验证 401 Provider 错误会回退到本地只读助手并给出警告。
- 浏览器端到端验证每日汇总与七天趋势均展示真实工具证据。

最新全量回归：后端 62 个通过、3 个环境相关测试跳过，综合覆盖率 79%；前端 16 个套件、48 个测试通过。

## 7. 当前边界与下一步

对话与消息现已按用户保存在 PostgreSQL 中，最近 8 条消息用于理解追问，但事实必须在当前轮重新调用工具。具体裁剪、幂等、隐私与删除边界见 [AI 对话状态与消息持久化](CONVERSATION_STATE.md)。个性化周报、流式输出、真实 OpenAI Key 多轮评测和线上反馈指标仍是后续任务；不能将当前实现描述成无限上下文、完整自主 Agent 或医疗建议系统。
