from uuid import uuid4

from httpx2 import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import OpenAIResponsesWeeklyReportProvider, ProviderError
from app.models import AiCallLog


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
    assert body["provider"] == "rule_based_weekly_report_v1"
    assert body["fallback_used"] is False
    assert body["facts"]["current"]["days_with_records"] == 4
    assert body["facts"]["current"]["total_kcal"] == 800
    assert body["facts"]["previous"]["total_kcal"] == 400
    assert body["facts"]["comparison_available"] is True
    assert body["facts"]["changes"]["average_kcal_percent"] == 100
    assert body["data_fingerprint"] and len(body["data_fingerprint"]) == 64
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
