from copy import deepcopy
from uuid import uuid4

from httpx2 import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import OpenAIResponsesAssistantProvider, ProviderError
from app.models import AiCallLog

PROFILE = {
    "gender": "male",
    "age": 25,
    "height_cm": 175,
    "weight_kg": 70,
    "activity_level": "moderate",
    "goal": "maintain",
}

FOOD = {
    "name": "燕麦片",
    "brand": "Private Brand",
    "category": "grain",
    "serving_unit": "份",
    "serving_weight_g": 40,
    "kcal_per_100g": 380,
    "protein_per_100g": 13,
    "fat_per_100g": 7,
    "carbs_per_100g": 68,
    "sugar_per_100g": 1,
    "sodium_per_100g": 5,
    "caffeine_per_100g": 0,
}


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def log_payload(kcal: float, log_date: str = "2026-07-19") -> dict[str, object]:
    return {
        "client_id": str(uuid4()),
        "log_date": log_date,
        "meal_type": "lunch",
        "custom_name": "测试餐",
        "amount": 1,
        "unit": "份",
        "nutrition": {
            "kcal": kcal,
            "protein": 20,
            "fat": 10,
            "carbs": 30,
            "sugar": 2,
            "sodium": 300,
            "caffeine": 0,
        },
        "note": None,
    }


async def ask(client: AsyncClient, headers: dict[str, str], question: str):
    return await client.post(
        "/api/v1/ai/assistant:answer",
        headers=headers,
        json={"question": question, "reference_date": "2026-07-19", "locale": "zh-CN"},
    )


async def test_assistant_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/ai/assistant:answer",
        json={"question": "我今天吃得怎么样？", "reference_date": "2026-07-19"},
    )

    assert response.status_code == 401


async def test_local_assistant_cites_user_scoped_daily_summary(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = await register(api_client, "assistant-owner@example.com")
    await api_client.put("/api/v1/users/me/profile", headers=owner, json=PROFILE)
    await api_client.post("/api/v1/logs", headers=owner, json=log_payload(520))
    other = await register(api_client, "assistant-other@example.com")
    await api_client.post("/api/v1/logs", headers=other, json=log_payload(999))

    response = await ask(api_client, owner, "我今天吃得怎么样？")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "rule_based_assistant_v1"
    assert body["fallback_used"] is False
    assert body["prompt_version"] == "rule-nutrition-assistant-v1.1.0"
    assert body["trace_id"] is not None
    assert body["evidence"][0]["tool_name"] == "get_today_summary"
    assert "520 kcal" in body["evidence"][0]["summary"]
    assert "999" not in body["answer"]
    assert body["usage"]["total_tokens"] == 0

    async with session_factory() as session:
        call_log = await session.scalar(
            select(AiCallLog).where(AiCallLog.user_id.is_not(None)).order_by(AiCallLog.created_at)
        )
    assert call_log is not None
    assert call_log.operation == "assistant_question"


async def test_weekly_tool_uses_fixed_seven_day_window(api_client: AsyncClient) -> None:
    headers = await register(api_client, "assistant-week@example.com")
    await api_client.post("/api/v1/logs", headers=headers, json=log_payload(700, "2026-07-19"))
    second = deepcopy(log_payload(350, "2026-07-15"))
    await api_client.post("/api/v1/logs", headers=headers, json=second)
    zero_kcal = deepcopy(log_payload(0, "2026-07-16"))
    await api_client.post("/api/v1/logs", headers=headers, json=zero_kcal)

    response = await ask(api_client, headers, "帮我看看最近七天趋势")

    assert response.status_code == 200
    evidence = response.json()["evidence"][0]
    assert evidence["tool_name"] == "get_weekly_trend"
    assert "2026-07-13 至 2026-07-19" in evidence["summary"]
    assert "3/7 天" in evidence["summary"]
    assert "1050 kcal" in evidence["summary"]


async def test_food_search_tool_cannot_see_another_users_private_food(
    api_client: AsyncClient,
) -> None:
    owner = await register(api_client, "assistant-food-owner@example.com")
    other = await register(api_client, "assistant-food-other@example.com")
    await api_client.post("/api/v1/foods", headers=owner, json=FOOD)

    owner_response = await ask(api_client, owner, "查询燕麦片的营养")
    other_response = await ask(api_client, other, "查询燕麦片的营养")

    assert "找到 1 项" in owner_response.json()["evidence"][0]["summary"]
    assert "未找到" in other_response.json()["evidence"][0]["summary"]


async def test_invalid_user_api_key_falls_back_to_local_assistant(
    api_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    headers = await register(api_client, "assistant-invalid-key@example.com")
    api_key = "fake-invalid-openai-key-1234567890"
    response = await api_client.put(
        "/api/v1/ai/credentials",
        headers=headers,
        json={"api_key": api_key},
    )
    assert response.status_code == 200

    async def reject_invalid_key(
        provider: OpenAIResponsesAssistantProvider,
        *_: object,
    ) -> object:
        assert provider.api_key == api_key
        raise ProviderError("http_401", "invalid key", retryable=False)

    monkeypatch.setattr(OpenAIResponsesAssistantProvider, "answer", reject_invalid_key)
    response = await ask(api_client, headers, "我今天吃得怎么样？")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "rule_based_assistant_v1"
    assert body["fallback_used"] is True
    assert body["evidence"][0]["tool_name"] == "get_today_summary"
    assert "凭证无效" in body["warnings"][0]
