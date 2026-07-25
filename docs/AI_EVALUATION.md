# AI 饮食实体抽取评测与回归

## 1. 这套评测解决什么问题

“模型能返回 JSON”只说明接口可解析，不能证明食物、数量、单位和餐次正确。本项目把 AI 抽取质量拆成可重复测量的指标，并在 Prompt、模型或规则变化后运行同一份版本化数据集。

当前先建立本地评测框架和规则降级 Provider 基线。真实 OpenAI 模型必须由开发者显式允许付费并提供环境变量 Key 后单独运行；项目不会把规则结果冒充成真实模型结果。

OpenAI 官方文档也把 Evals 定义为用指定的内容和风格标准测试模型输出，并强调在升级或尝试新模型时评测是可靠应用的重要组成部分。当前项目采用本地评测器，后续数据量和团队规模扩大后可迁移或同步到托管 Evals API。

## 2. 文件结构与可复现输入

- `backend/evals/food_text_v1.json`：26 条脱敏中文样本，共 32 个期望实体。
- `backend/app/evals/`：Pydantic 数据契约、匹配逻辑、指标计算和 JSON 报告。
- `backend/evals/baselines/rule_based_v1.json`：规则降级 Provider 的最低回归门槛。
- `backend/evals/reports/rule_based_v1.json`：2026-07-19 本地原始报告，含逐条失败样本。
- `backend/scripts/run_ai_eval.py`：规则或 OpenAI Provider 的统一 CLI。
- `backend/tests/test_ai_evaluation.py`：固定质量结果和指标分母的自动化测试。

数据集不是只覆盖“会答的题”，还包含：多实体、中文数量、克/千克换算、餐次提示、缺少数量、目录外食物、品牌饮品、菜名与食材边界、否定、过敏描述、未来计划和无食物文本。

## 3. 指标定义

### 实体级指标

实体先按 Unicode NFKC、去空白、大小写折叠后的 `normalized_name` 匹配。

- Precision = TP / (TP + FP)：返回的实体中有多少是真的。
- Recall = TP / (TP + FN)：期望实体中有多少被找到。
- F1 = Precision 与 Recall 的调和平均。
- 数量、单位、餐次准确率：只在名称匹配成功的实体上计算，避免把“名称识别失败”和“字段提取失败”重复惩罚。
- Case Exact Match：一条输入的实体集合完全一致，并且所有匹配实体的数量、单位和餐次全部正确。

### 可靠性与工程指标

- 请求成功率：所有样本中 Provider 成功返回强类型结果的比例。
- Schema 合法率：只以“成功返回”与“Schema/空响应错误”为分母；网络失败不伪装成格式错误，而是只影响请求成功率。
- P50/P95 延迟：使用 nearest-rank 百分位；本地规则耗时不能代表公网模型耗时。
- Token 与成本：汇总 Provider 返回的输入/输出 Token。只有同时显式配置输入和输出单价时才估算成本，否则保持 `null`。

## 4. 当前真实基线

测试环境：Windows 本机、Python 3.12 虚拟环境、`rule_based_v1`、数据集 `food-text-zh-cn-v1.0.0`。

| 指标                                   |                     结果 |
| -------------------------------------- | -----------------------: |
| 样本数 / 期望实体数                    |                  26 / 32 |
| 请求成功率                             |                     100% |
| Schema 合法率                          |                     100% |
| TP / FP / FN                           |               26 / 6 / 6 |
| 实体 Precision / Recall / F1           | 81.25% / 81.25% / 81.25% |
| 数量 / 单位 / 餐次准确率（名称匹配后） |       100% / 100% / 100% |
| Case Exact Match                       |                   65.38% |
| Token / 成本                           |   0 / 不适用（本地规则） |

失败样本集中在三类：

1. 规则目录外的饺子、品牌奶茶、炸鸡和美式咖啡无法召回。
2. “麻婆豆腐”被错误缩成“豆腐”，“普通面包”被过度标准化为“全麦面包”。
3. “没吃鸡蛋”“对牛奶过敏”“计划明天吃苹果”被误判为已经摄入。

这些失败不在本阶段直接修掉，因为首要目标是先建立稳定测量工具。下一次改规则或 Prompt 时，必须同时观察召回是否提高、误报是否增加，而不是凭几个演示句判断。

## 5. 运行方式

从仓库根目录运行免费、确定性的规则评测和回归门禁：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\run_ai_eval.py `
  --output backend\evals\reports\rule_based_v1.json `
  --baseline backend\evals\baselines\rule_based_v1.json
```

使用自己的 OpenAI Key 测真实模型：

```powershell
$env:NUTRIPILOT_OPENAI_API_KEY = "your-key"
$env:NUTRIPILOT_OPENAI_MODEL = "gpt-5.6-luna"
backend\.venv\Scripts\python.exe backend\scripts\run_ai_eval.py `
  --provider openai `
  --allow-paid-api `
  --output backend\evals\reports\openai_luna_v1.json
Remove-Item Env:NUTRIPILOT_OPENAI_API_KEY
```

CLI 故意不提供 `--api-key` 参数，避免 Key 进入命令历史；没有 `--allow-paid-api` 时也拒绝真实调用。可用 `--max-cases 3` 先做小样本冒烟，再运行完整数据集。

如需成本估算，再显式提供当次确认过的每百万 Token 单价：

```powershell
$env:NUTRIPILOT_AI_INPUT_PRICE_PER_MILLION_USD = "已核对的输入单价"
$env:NUTRIPILOT_AI_OUTPUT_PRICE_PER_MILLION_USD = "已核对的输出单价"
```

## 6. 局限与下一步

- 26 条样本适合作为首版回归集，不足以代表真实用户的长尾分布。
- 标签由项目开发者编写，尚未做双人标注和一致性检验。
- 当前名称采用严格标准名匹配，同义标准名可能被判错；扩大数据集后可增加受控别名，而不是使用过度宽松的模糊匹配。
- 用户直接接受率、字段修改率需要确认页面记录匿名反馈后才能测，不能由离线集推断。
- 当前报告串行调用以提高可复现性；生产延迟和吞吐需要另做并发与真实网络测试。
- 报告记录数据集、Provider、实际响应模型和 Prompt 版本；改动 Prompt 时必须提升版本并生成新报告。

参考：[OpenAI Evals 指南](https://developers.openai.com/api/docs/guides/evals)、[OpenAI Structured Outputs 指南](https://developers.openai.com/api/docs/guides/structured-outputs)。
