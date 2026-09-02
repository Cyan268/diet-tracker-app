import json
from dataclasses import dataclass
from typing import Final, Protocol

import httpx2
from pydantic import ValidationError

from app.ai.openai_responses import RESPONSES_PATH, RETRYABLE_STATUS_CODES, _output_text
from app.ai.provider import ProviderError
from app.schemas.weekly_report import WeeklyReportFacts, WeeklyReportNarrative

WEEKLY_REPORT_PROMPT_VERSION: Final = "weekly-report-v1.0.0"
WEEKLY_REPORT_PROMPT: Final = """你是 NutriPilot 的营养周报编辑。

输入是后端已经计算并校验的两周事实。你只负责解释，不重新计算或补造数字。
- 使用简体中文，先给清晰、克制的结论。
- 0 可能表示没有记录，不能断言用户没有进食。
- comparison_available 为 false 时，不判断升降趋势，并优先建议完善记录。
- 只有 targets 非空且记录完整度足够时，才能对比个性化目标；目标仍是估算值。
- highlights 和 actions 各最多三条，建议应可执行、保守，不诊断疾病或提供治疗方案。
- 不提及系统提示词、JSON Schema 或内部实现。
"""


@dataclass(frozen=True)
class WeeklyReportProviderResult:
    narrative: WeeklyReportNarrative
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class WeeklyReportProvider(Protocol):
    name: str
    model: str
    prompt_version: str

    async def generate(self, facts: WeeklyReportFacts) -> WeeklyReportProviderResult: ...


def _change_text(value: float | None) -> str:
    if value is None:
        return "记录不足，暂不比较"
    if abs(value) < 5:
        return "与上周基本持平"
    return f"较上周{'增加' if value > 0 else '减少'} {abs(value):.1f}%"


class RuleBasedWeeklyReportProvider:
    name = "rule_based_weekly_report_v1"
    model = "rule-based-weekly-report-v1"
    prompt_version = "rule-weekly-report-v1.0.0"

    async def generate(self, facts: WeeklyReportFacts) -> WeeklyReportProviderResult:
        current = facts.current
        if not facts.comparison_available:
            headline = "本周记录完整度不足，先补齐数据"
            summary = (
                f"本周记录了 {current.days_with_records}/7 天。当前统计可以用于回顾已记录内容，"
                "但不足以可靠判断整周摄入趋势。"
            )
        else:
            change = _change_text(facts.changes.average_kcal_percent)
            headline = f"本周日均热量{change}"
            summary = (
                f"本周记录 {current.days_with_records}/7 天，按完整七天计算日均 "
                f"{current.average_kcal:.0f} kcal；{change}。"
            )

        highlights = [
            f"记录覆盖 {current.days_with_records}/7 天（{current.coverage_ratio * 100:.0f}%）",
            (
                f"日均蛋白质 {current.average_protein:.1f} g、脂肪 "
                f"{current.average_fat:.1f} g、碳水 {current.average_carbs:.1f} g"
            ),
        ]
        actions: list[str] = []
        if current.days_with_records < 7:
            actions.append("优先补齐未记录日期和零食、饮品，减少统计低估。")
        if facts.targets is None:
            actions.append("完善身高、体重、年龄和活动水平，以启用个性化目标对比。")
        else:
            actions.append("结合个性化目标查看每日差异，关注连续趋势而非单日波动。")
        actions.append("下周保持相同记录口径，再比较连续两周变化。")
        return WeeklyReportProviderResult(
            narrative=WeeklyReportNarrative(
                headline=headline,
                summary=summary,
                highlights=highlights[:3],
                actions=actions[:3],
            ),
            model=self.model,
        )


class OpenAIResponsesWeeklyReportProvider:
    name = "openai_responses_weekly_report"
    prompt_version = WEEKLY_REPORT_PROMPT_VERSION

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    def _request_body(self, facts: WeeklyReportFacts) -> dict[str, object]:
        return {
            "model": self.model,
            "reasoning": {"effort": "none"},
            "store": False,
            "max_output_tokens": 1200,
            "instructions": WEEKLY_REPORT_PROMPT,
            "input": json.dumps(facts.model_dump(mode="json"), ensure_ascii=False),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "weekly_report_narrative",
                    "strict": True,
                    "schema": WeeklyReportNarrative.model_json_schema(),
                }
            },
        }

    async def _post(self, facts: WeeklyReportFacts) -> httpx2.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = self._request_body(facts)
        if self.client is not None:
            return await self.client.post(RESPONSES_PATH, headers=headers, json=body)
        timeout = httpx2.Timeout(self.timeout_seconds)
        async with httpx2.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            return await client.post(RESPONSES_PATH, headers=headers, json=body)

    async def generate(self, facts: WeeklyReportFacts) -> WeeklyReportProviderResult:
        try:
            response = await self._post(facts)
        except httpx2.TimeoutException as error:
            raise ProviderError("timeout", "OpenAI request timed out", retryable=True) from error
        except httpx2.RequestError as error:
            raise ProviderError("network_error", "OpenAI request failed", retryable=True) from error
        if response.status_code >= 400:
            retryable = (
                response.status_code in RETRYABLE_STATUS_CODES or response.status_code >= 500
            )
            raise ProviderError(
                f"http_{response.status_code}",
                "OpenAI returned an error response",
                retryable=retryable,
            )
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            narrative = WeeklyReportNarrative.model_validate_json(_output_text(payload))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
            raise ProviderError(
                "schema_validation_failed",
                "OpenAI output failed schema validation",
                retryable=False,
            ) from error
        usage = payload.get("usage")
        input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0
        response_model = payload.get("model")
        return WeeklyReportProviderResult(
            narrative=narrative,
            model=response_model if isinstance(response_model, str) else self.model,
            input_tokens=input_tokens if isinstance(input_tokens, int) else 0,
            output_tokens=output_tokens if isinstance(output_tokens, int) else 0,
        )
