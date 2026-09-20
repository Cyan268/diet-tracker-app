from uuid import uuid4

from httpx2 import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import (
    OpenAIResponsesWeeklyReportProvider,
    ProviderError,
    WeeklyReportProviderResult,
)
from app.models import AiCallLog
from app.schemas.weekly_report import WeeklyReportNarrative


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def log_payload(kcal: float, log_date: str) -> dict[str, object]:
    return {
        "client_id": str(uuid4()),
        "log_date": log_date,
        "meal_type": "lunch",
        "custom_name": "周报测试餐",
        "amount": 1,
        "unit": "份",
        "nutrition": {
            "kcal": kcal,
            "protein": kcal / 10,
            "fat": kcal / 20,
            "carbs": kcal / 5,
            "sugar": 2,
            "sodium": 300,
            "caffeine": 0,
        },
        "note": None,
    }


async def generate(client: AsyncClient, headers: dict[str, str]):
    return await client.post(
        "/api/v1/ai/reports/weekly:generate",
        headers=headers,
        json={"end_date": "2026-07-20", "locale": "zh-CN"},
    )


async def test_weekly_report_requires_authentication(api_client: AsyncClient) -> None:
    response = await generate(api_client, {})
    assert response.status_code == 401


async def test_weekly_report_uses_user_scoped_two_week_facts_and_logs_call(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = await register(api_client, "weekly-owner@example.com")
    other = await register(api_client, "weekly-other@example.com")
    current_dates = ["2026-07-14", "2026-07-16", "2026-07-18", "2026-07-20"]
    previous_dates = ["2026-07-07", "2026-07-09", "2026-07-11", "2026-07-13"]
    for log_date in current_dates:
        await api_client.post("/api/v1/logs", headers=owner, json=log_payload(200, log_date))
    for log_date in previous_dates:
        await api_client.post("/api/v1/logs", headers=owner, json=log_payload(100, log_date))
    await api_client.post("/api/v1/logs", headers=other, json=log_payload(9999, "2026-07-20"))

    response = await generate(api_client, owner)

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "2.0"
    assert body["provider"] == "rule_based_weekly_report_v1"
    assert body["fallback_used"] is False
    assert body["facts"]["current"]["days_with_records"] == 4
    assert body["facts"]["current"]["total_kcal"] == 800
    assert body["facts"]["current"]["average_kcal"] == 114.29
    assert body["facts"]["current"]["recorded_day_average_kcal"] == 200
    assert body["facts"]["previous"]["total_kcal"] == 400
    assert body["facts"]["comparison_available"] is True
    assert body["facts"]["changes"]["average_kcal_percent"] == 100
    assert body["data_fingerprint"] and len(body["data_fingerprint"]) == 64
    assert body["facts"]["business_date_basis"] == "user_supplied_log_date"
    assert body["facts"]["completeness_threshold_days"] == 4
    assert {reference["id"] for reference in body["facts"]["fact_references"]} >= {
        "current.days_with_records",
        "current.average_kcal",
        "current.recorded_day_average_kcal",
        "changes.average_kcal_percent",
    }
    assert all(body["narrative"]["citations"])
    structure = {item["meal_type"]: item for item in body["facts"]["meal_structure"]}
    assert structure["lunch"]["log_count"] == 4
    assert structure["lunch"]["kcal_ratio"] == 1
    assert structure["drink"]["kcal_ratio"] == 0
    assert body["facts"]["target_adherence"]["available"] is False
    assert "9999" not in str(body)
    assert body["trace_id"] is not None

    async with session_factory() as session:
        call = await session.scalar(select(AiCallLog).where(AiCallLog.operation == "weekly_report"))
    assert call is not None
    assert call.user_id is not None


async def test_weekly_report_with_incomplete_data_disables_comparison(
    api_client: AsyncClient,
) -> None:
    headers = await register(api_client, "weekly-incomplete@example.com")
    await api_client.post("/api/v1/logs", headers=headers, json=log_payload(500, "2026-07-20"))

    response = await generate(api_client, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["facts"]["comparison_available"] is False
    assert body["facts"]["changes"]["average_kcal_percent"] is None
    assert body["facts"]["current"]["average_kcal"] == 71.43
    assert body["facts"]["current"]["recorded_day_average_kcal"] == 500
    assert "记录完整度不足" in body["narrative"]["headline"]
    assert any("少于 4 天" in warning for warning in body["warnings"])


async def test_invalid_user_key_falls_back_to_rule_weekly_report(
    api_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    headers = await register(api_client, "weekly-invalid-key@example.com")
    api_key = "fake-invalid-openai-key-1234567890"
    await api_client.put("/api/v1/ai/credentials", headers=headers, json={"api_key": api_key})

    async def reject_key(
        provider: OpenAIResponsesWeeklyReportProvider,
        *_: object,
    ) -> object:
        assert provider.api_key == api_key
        raise ProviderError("http_401", "invalid key", retryable=False)

    monkeypatch.setattr(OpenAIResponsesWeeklyReportProvider, "generate", reject_key)
    response = await generate(api_client, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["fallback_used"] is True
    assert body["provider"] == "rule_based_weekly_report_v1"
    assert "凭证无效" in body["warnings"][0]


async def test_target_adherence_is_an_explicit_product_rule(
    api_client: AsyncClient,
) -> None:
    headers = await register(api_client, "weekly-target-rule@example.com")
    profile_response = await api_client.put(
        "/api/v1/users/me/profile",
        headers=headers,
        json={
            "gender": "male",
            "age": 25,
            "height_cm": 175,
            "weight_kg": 70,
            "activity_level": "moderate",
            "goal": "maintain",
        },
    )
    target_kcal = profile_response.json()["daily_targets"]["kcal"]
    for log_date in ("2026-07-14", "2026-07-16", "2026-07-18", "2026-07-20"):
        await api_client.post(
            "/api/v1/logs",
            headers=headers,
            json=log_payload(target_kcal, log_date),
        )

    response = await generate(api_client, headers)

    assert response.status_code == 200
    adherence = response.json()["facts"]["target_adherence"]
    assert adherence == {
        "available": True,
        "assessment_days": 4,
        "kcal_within_target_days": 4,
        "tolerance_percent": 10,
        "rule": "recorded_day_kcal_within_target_plus_or_minus_10_percent",
    }
    assert any(
        reference["id"] == "target.kcal_within_range_days"
        for reference in response.json()["facts"]["fact_references"]
    )


async def test_zero_kcal_log_is_recorded_but_not_target_attainment(
    api_client: AsyncClient,
) -> None:
    headers = await register(api_client, "weekly-zero-kcal@example.com")
    profile_response = await api_client.put(
        "/api/v1/users/me/profile",
        headers=headers,
        json={
            "gender": "female",
            "age": 25,
            "height_cm": 165,
            "weight_kg": 55,
            "activity_level": "light",
            "goal": "maintain",
        },
    )
    target_kcal = profile_response.json()["daily_targets"]["kcal"]
    for log_date, kcal in (
        ("2026-07-14", target_kcal),
        ("2026-07-16", target_kcal),
        ("2026-07-18", target_kcal),
        ("2026-07-20", 0),
    ):
        await api_client.post(
            "/api/v1/logs",
            headers=headers,
            json=log_payload(kcal, log_date),
        )

    response = await generate(api_client, headers)

    adherence = response.json()["facts"]["target_adherence"]
    assert response.json()["facts"]["current"]["days_with_records"] == 4
    assert adherence["assessment_days"] == 4
    assert adherence["kcal_within_target_days"] == 3


async def test_unsupported_model_number_falls_back_to_cited_rule_report(
    api_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    headers = await register(api_client, "weekly-fabricated-number@example.com")
    await api_client.put(
        "/api/v1/ai/credentials",
        headers=headers,
        json={"api_key": "fake-fact-validation-key-1234567890"},
    )
    await api_client.post(
        "/api/v1/logs",
        headers=headers,
        json=log_payload(500, "2026-07-20"),
    )

    async def fabricate_number(*_: object) -> WeeklyReportProviderResult:
        return WeeklyReportProviderResult(
            narrative=WeeklyReportNarrative(
                headline="本周日均热量 9999 kcal",
                summary="本周记录事实已经完成汇总。",
                highlights=["记录覆盖情况已经计算。"],
                actions=["继续记录。"],
                citations=[
                    {"path": "headline", "fact_ids": ["current.average_kcal"]},
                    {"path": "summary", "fact_ids": ["current.days_with_records"]},
                    {"path": "highlights.0", "fact_ids": ["current.coverage_ratio"]},
                ],
            ),
            model="fabricating-model",
        )

    monkeypatch.setattr(OpenAIResponsesWeeklyReportProvider, "generate", fabricate_number)

    response = await generate(api_client, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["fallback_used"] is True
    assert body["provider"] == "rule_based_weekly_report_v1"
    assert "9999" not in str(body["narrative"])
    assert "事实引用校验" in body["warnings"][0]
