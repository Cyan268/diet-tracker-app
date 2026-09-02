import json
from datetime import date

import httpx2
import pytest

from app.ai import OpenAIResponsesWeeklyReportProvider, ProviderError
from app.schemas.weekly_report import (
    WeeklyMetricChanges,
    WeeklyPeriodSummary,
    WeeklyReportFacts,
)


def facts() -> WeeklyReportFacts:
    current = WeeklyPeriodSummary(
        start_date=date(2026, 7, 14),
        end_date=date(2026, 7, 20),
        days_with_records=7,
        coverage_ratio=1,
        total_kcal=12600,
        average_kcal=1800,
        average_protein=90,
        average_fat=55,
        average_carbs=220,
        average_sugar=30,
        average_sodium=1800,
        average_caffeine=120,
    )
    previous = current.model_copy(
        update={
            "start_date": date(2026, 7, 7),
            "end_date": date(2026, 7, 13),
            "average_kcal": 1700,
            "total_kcal": 11900,
        }
    )
    return WeeklyReportFacts(
        current=current,
        previous=previous,
        targets=None,
        comparison_available=True,
        changes=WeeklyMetricChanges(
            average_kcal_percent=5.9,
            average_protein_percent=0,
            average_fat_percent=0,
            average_carbs_percent=0,
            average_sugar_percent=0,
            average_sodium_percent=0,
            average_caffeine_percent=0,
        ),
    )


def provider(transport: httpx2.MockTransport) -> OpenAIResponsesWeeklyReportProvider:
    return OpenAIResponsesWeeklyReportProvider(
        api_key="test-key",
        model="gpt-5.6-luna",
        base_url="https://api.openai.com/v1",
        timeout_seconds=8,
        client=httpx2.AsyncClient(transport=transport, base_url="https://api.openai.com/v1"),
    )


async def test_weekly_report_provider_uses_strict_schema_and_parses_usage() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert json.loads(body["input"])["current"]["average_kcal"] == 1800
        narrative = {
            "headline": "本周摄入整体平稳",
            "summary": "本周记录完整，可结合连续趋势进行观察。",
            "highlights": ["日均热量 1800 kcal"],
            "actions": ["继续完整记录饮品和零食。"],
        }
        return httpx2.Response(
            200,
            json={
                "model": "gpt-5.6-luna-2026-07-01",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(narrative, ensure_ascii=False),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 200, "output_tokens": 60},
            },
        )

    result = await provider(httpx2.MockTransport(handler)).generate(facts())
    assert result.model == "gpt-5.6-luna-2026-07-01"
    assert result.input_tokens == 200
    assert result.output_tokens == 60
    assert result.narrative.headline == "本周摄入整体平稳"


async def test_weekly_report_provider_rejects_invalid_shape() -> None:
    async def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ]
            },
        )

    with pytest.raises(ProviderError) as caught:
        await provider(httpx2.MockTransport(handler)).generate(facts())
    assert caught.value.code == "schema_validation_failed"
