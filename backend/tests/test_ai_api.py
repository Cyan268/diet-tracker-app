from decimal import Decimal

from httpx2 import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import OpenAIResponsesFoodTextProvider, ProviderResult
from app.core.config import Settings, get_settings
from app.main import app
from app.models import AiCallLog, AiCredential, User
from app.schemas.ai import ParsedFoodEntity


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_food_text_analysis_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/ai/food-text:analyze",
        json={"text": "午餐吃了200克鸡胸肉", "log_date": "2026-07-17"},
    )

    assert response.status_code == 401


async def test_food_text_analysis_returns_structured_confirmable_draft(
    api_client: AsyncClient,
) -> None:
    headers = await register(api_client, "ai-text@example.com")

    response = await api_client.post(
        "/api/v1/ai/food-text:analyze",
        headers=headers,
        json={
            "text": "午餐吃了200克鸡胸肉和1碗米饭",
            "log_date": "2026-07-17",
            "locale": "zh-CN",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["requires_confirmation"] is True
    assert body["provider"] == "rule_based_v1"
    assert body["model"] == "rule-based-v1"
    assert body["fallback_used"] is False
    assert body["latency_ms"] >= 0
    assert body["trace_id"] is not None
    assert body["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": None,
    }
    assert body["warnings"] == []
    assert body["entities"] == [
        {
            "raw_name": "鸡胸肉",
            "normalized_name": "鸡胸肉（水煮）",
            "amount": 200.0,
            "unit": "g",
            "meal_type": "lunch",
            "confidence": 0.94,
            "needs_review": False,
            "evidence": "识别到“鸡胸肉”及其相邻数量",
        },
        {
            "raw_name": "米饭",
            "normalized_name": "白米饭",
            "amount": 1.0,
            "unit": "碗",
            "meal_type": "lunch",
            "confidence": 0.94,
            "needs_review": False,
            "evidence": "识别到“米饭”及其相邻数量",
        },
    ]


async def test_food_text_analysis_marks_inferred_quantity_for_review(
    api_client: AsyncClient,
) -> None:
    headers = await register(api_client, "ai-review@example.com")

    response = await api_client.post(
        "/api/v1/ai/food-text:analyze",
        headers=headers,
        json={"text": "早上吃了香蕉", "log_date": "2026-07-17"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entities"][0]["amount"] == 1
    assert body["entities"][0]["unit"] == "根"
    assert body["entities"][0]["needs_review"] is True
    assert body["entities"][0]["confidence"] == 0.68
    assert len(body["warnings"]) == 1


async def test_food_text_analysis_returns_warning_instead_of_inventing_food(
    api_client: AsyncClient,
) -> None:
    headers = await register(api_client, "ai-unknown@example.com")

    response = await api_client.post(
        "/api/v1/ai/food-text:analyze",
        headers=headers,
        json={"text": "今天吃了一份神秘料理", "log_date": "2026-07-17"},
    )

    assert response.status_code == 200
    assert response.json()["entities"] == []
    assert "没有识别到" in response.json()["warnings"][0]


async def test_ai_metrics_are_user_scoped_and_prompt_is_only_stored_as_hash(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await register(api_client, "ai-metrics@example.com")
    prompt = "午餐吃了200克鸡胸肉"

    for _ in range(2):
        response = await api_client.post(
            "/api/v1/ai/food-text:analyze",
            headers=headers,
            json={"text": prompt, "log_date": "2026-07-17"},
        )
        assert response.status_code == 200

    response = await api_client.get("/api/v1/ai/metrics", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_calls"] == 2
    assert body["successful_calls"] == 2
    assert body["fallback_calls"] == 0
    assert body["failed_calls"] == 0
    assert body["total_tokens"] == 0
    assert Decimal(str(body["estimated_cost_usd"])) == 0
    assert body["unpriced_calls"] == 0

    async with session_factory() as session:
        logs = list((await session.scalars(select(AiCallLog))).all())
    assert len(logs) == 2
    assert all(log.input_sha256 != prompt for log in logs)
    assert all(len(log.input_sha256) == 64 for log in logs)


async def test_user_can_store_read_and_delete_encrypted_ai_credential(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_headers = await register(api_client, "ai-key-owner@example.com")
    other_headers = await register(api_client, "ai-key-other@example.com")
    api_key = "fake-openai-key-for-tests-1234567890"

    response = await api_client.put(
        "/api/v1/ai/credentials",
        headers=owner_headers,
        json={"api_key": api_key},
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["key_hint"] == "••••7890"
    assert api_key not in response.text

    response = await api_client.get("/api/v1/ai/credentials", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["key_hint"] == "••••7890"

    response = await api_client.get("/api/v1/ai/credentials", headers=other_headers)
    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "provider": "openai",
        "key_hint": None,
        "updated_at": None,
    }

    async with session_factory() as session:
        credential = await session.scalar(select(AiCredential))
    assert credential is not None
    assert api_key.encode() not in credential.encrypted_api_key

    response = await api_client.delete("/api/v1/ai/credentials", headers=owner_headers)
    assert response.status_code == 204
    response = await api_client.get("/api/v1/ai/credentials", headers=owner_headers)
    assert response.json()["configured"] is False


async def test_configured_user_credential_selects_openai_provider(
    api_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    headers = await register(api_client, "ai-key-runtime@example.com")
    api_key = "fake-openai-runtime-key-1234567890"
    response = await api_client.put(
        "/api/v1/ai/credentials",
        headers=headers,
        json={"api_key": api_key},
    )
    assert response.status_code == 200

    async def fake_extract(
        provider: OpenAIResponsesFoodTextProvider,
        _: object,
    ) -> ProviderResult:
        assert provider.api_key == api_key
        return ProviderResult(
            entities=[
                ParsedFoodEntity(
                    raw_name="鸡胸肉",
                    normalized_name="鸡胸肉（水煮）",
                    amount=200,
                    unit="g",
                    meal_type="lunch",
                    confidence=0.97,
                    needs_review=False,
                    evidence="模型识别到200克鸡胸肉",
                )
            ],
            model="mock-openai-model",
            input_tokens=80,
            output_tokens=20,
        )

    monkeypatch.setattr(OpenAIResponsesFoodTextProvider, "extract", fake_extract)
    response = await api_client.post(
        "/api/v1/ai/food-text:analyze",
        headers=headers,
        json={"text": "午餐吃了200克鸡胸肉", "log_date": "2026-07-18"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai_responses"
    assert body["model"] == "mock-openai-model"
    assert body["fallback_used"] is False
    assert body["usage"]["total_tokens"] == 100


async def test_demo_account_cannot_store_credentials_or_use_server_openai_key(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await register(api_client, "demo-ai@example.com")
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "demo-ai@example.com"))
        assert user is not None
        user.is_demo = True
        await session.commit()

    settings = Settings(
        _env_file=None,
        ai_provider="openai",
        openai_api_key="fake-server-openai-key-1234567890",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    status_response = await api_client.get("/api/v1/ai/credentials", headers=headers)
    put_response = await api_client.put(
        "/api/v1/ai/credentials",
        headers=headers,
        json={"api_key": "fake-user-openai-key-1234567890"},
    )
    delete_response = await api_client.delete("/api/v1/ai/credentials", headers=headers)
    analyze_response = await api_client.post(
        "/api/v1/ai/food-text:analyze",
        headers=headers,
        json={"text": "午餐吃了200克鸡胸肉", "log_date": "2026-07-22"},
    )

    assert status_response.status_code == 200
    assert status_response.json()["configured"] is False
    assert put_response.status_code == 403
    assert delete_response.status_code == 403
    assert analyze_response.status_code == 200
    assert analyze_response.json()["provider"] == "rule_based_v1"
