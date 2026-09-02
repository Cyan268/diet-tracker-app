# 个性化 AI 营养周报

## 1. 功能目标

周报汇总截至用户所选日期的最近 7 天，并与再前 7 天对比。它不是让模型自由阅读数据库并计算营养，而是把职责拆成两层：

1. 后端按 JWT 用户 ID 查询记录，确定性计算日期窗口、记录天数、日均营养、个性化目标和周环比。
2. AI 只把已经校验的事实转成简体中文标题、总结、要点和行动建议。

接口为 `POST /api/v1/ai/reports/weekly:generate`。页面只在用户点击“生成本周周报”时调用，避免刷新统计页产生意外费用。

## 2. 数据与生成链路

```text
end_date + JWT user_id
  → 当前 7 天 / 上一 7 天用户隔离聚合
  → WeeklyReportFacts（Pydantic）
      ├─ current / previous
      ├─ days_with_records / coverage_ratio
      ├─ 7 天日均营养
      ├─ personalized targets（可空）
      └─ comparison_available / percent changes
  → SHA-256 事实指纹
  → OpenAI Structured Outputs / 本地规则 Provider
  → WeeklyReportNarrative（严格 Schema）
  → facts + narrative + warnings + trace/Token/延迟
```

OpenAI 路径使用 Responses API 的严格 JSON Schema；返回后仍由 Pydantic 再校验。官方 Structured Outputs 文档说明其目标是让输出遵循提供的 JSON Schema，但结构正确不能代替业务事实校验，因此数值计算仍留在确定性代码中：[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。

## 3. 记录完整度规则

- 每个窗口固定为 7 个自然日，缺失日补零以保持统计维度稳定。
- `days_with_records` 来自 SQL 实际返回的分组日期数；零热量记录仍算“有记录”。
- 日均值统一除以 7，不暗中只除以已记录天数，接口和界面明确标注“按 7 天”。
- 当前周和上一周都至少记录 4 天时才提供周环比。
- 上周日均为零时，百分比变化返回 `null`，避免制造无穷大或虚假的百分比。
- 记录少于 7 天时展示可能低估实际摄入的警告；0 不等于没有进食。

四天门槛是首版产品规则，不是医学标准。后续应结合用户记录习惯和真实反馈评估，而不是把它包装成科学结论。

## 4. 个性化与安全边界

若用户已经设置性别、年龄、身高、体重、活动水平和目标，事实层会带上确定性计算出的每日目标；未设置时明确返回 `targets: null`，周报只能描述记录，不能判断目标达成情况。

模型不能选择 `user_id`，也不能查询任意 SQL。用户身份来自 Bearer JWT，SQL 在服务端绑定当前账号。响应包含 `data_fingerprint`，它是规范化事实 JSON 的 SHA-256，可用来判断两次周报是否基于同一事实输入，但不用于恢复原始数据，也不能替代完整审计日志。

周报只提供生活记录参考，不诊断疾病、不提供治疗方案。API Key 仍沿用用户级加密凭证；无 Key 时直接使用本地规则周报，Key 无效、限流、超时或模型输出不合法时自动降级并显式展示原因。

## 5. 为什么不让模型返回完整周报数字

如果模型同时负责加总、比较和表达，会出现三类问题：同一数据多次调用可能算出不同数字；很难证明跨用户隔离；Schema 合法也无法证明算术正确。当前设计让数据库和 Python 负责可测试的数值，模型只生成受限文字。这牺牲了一部分“自由发挥”，换来可追溯、可降级、可测试的工程边界。

## 6. 测试范围

- 双用户不同数据，验证 SQL 聚合不串号。
- 当前周与上一周固定窗口、记录天数、总量与百分比。
- 数据不足或上周为零时不生成误导性环比。
- 无 Key 本地生成，以及无效 Key 自动降级和警告。
- Responses HTTP Mock 验证 `strict: true`、Schema、输入事实、Token 和模型版本。
- 前端纯函数验证环比、完整度和降级标签。

测试不调用真实付费模型。公网模型的文字质量、真实延迟和成本仍需用户显式配置 Key 后单独建立基线。
