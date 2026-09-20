import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from httpx2 import AsyncClient
from sqlalchemy import func, select

from app.models import (
    AnalysisConfirmation,
    AnalysisCorrection,
    AnalysisDraft,
    AnalysisEntity,
    AnalysisJob,
    FoodItem,
    FoodLog,
    User,
)
from app.schemas.analysis import AnalysisConfirmRequest
from app.services.analysis import confirm_analysis_draft
from app.services.catalog_seed import seed_global_catalog

FOOD = {
    "name": "苹果",
    "category": "fruit",
    "serving_unit": "个",
    "serving_weight_g": 200,
    "kcal_per_100g": 52,
    "protein_per_100g": 0.3,
    "fat_per_100g": 0.2,
    "carbs_per_100g": 14,
    "sugar_per_100g": 10,
    "sodium_per_100g": 1,
    "caffeine_per_100g": 0,
}


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def analysis_payload(request_id: UUID | None = None) -> dict[str, object]:
    return {
        "client_request_id": str(request_id or uuid4()),
        "text": "午餐吃了一个苹果",
        "log_date": "2026-09-14",
        "meal_type_hint": "lunch",
        "locale": "zh-CN",
    }


async def prepare_draft(api_client, session_factory, headers):
    food_response = await api_client.post("/api/v1/foods", headers=headers, json=FOOD)
    assert food_response.status_code == 201
    food = food_response.json()
    accepted = await api_client.post(
        "/api/v1/ai/analyses", headers=headers, json=analysis_payload()
    )
    assert accepted.status_code == 202
    job_id = UUID(accepted.json()["job_id"])
    draft_id = uuid4()
    entity_id = uuid4()
    async with session_factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None
        job.status = "succeeded"
        job.completed_at = datetime.now(UTC)
        draft = AnalysisDraft(
            id=draft_id,
            job_id=job.id,
            user_id=job.user_id,
            status="review",
            version=1,
            log_date=datetime(2026, 9, 14).date(),
            result_schema_version="draft-v1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(draft)
        await session.flush()
        session.add(
            AnalysisEntity(
                id=entity_id,
                draft_id=draft.id,
                position=0,
                raw_name="苹果",
                normalized_name="苹果",
                amount=Decimal("1"),
                unit="个",
                meal_type="lunch",
                confidence=Decimal("0.95"),
                needs_review=False,
                matched_food_id=UUID(food["id"]),
                catalog_revision=food["current_revision"],
                candidates=[
                    {
                        "food_item_id": food["id"],
                        "catalog_revision": food["current_revision"],
                        "name": food["name"],
                        "brand": food["brand"],
                        "source": food["source"],
                        "source_reference": food["source_reference"],
                        "nutrition_complete": food["nutrition_complete"],
                        "score": 1.0,
                        "reason": "canonical_exact",
                    }
                ],
            )
        )
        await session.commit()
    return job_id, draft_id, entity_id, food


async def test_analysis_submission_is_idempotent_isolated_and_cancellable(
    api_client: AsyncClient,
    session_factory,
) -> None:
    owner = await register(api_client, "analysis-owner@example.com")
    other = await register(api_client, "analysis-other@example.com")
    request_id = uuid4()
    payload = analysis_payload(request_id)

    created = await api_client.post("/api/v1/ai/analyses", headers=owner, json=payload)
    replay = await api_client.post("/api/v1/ai/analyses", headers=owner, json=payload)
    changed = dict(payload, text="晚餐吃了一个苹果")
    conflict = await api_client.post("/api/v1/ai/analyses", headers=owner, json=changed)

    assert created.status_code == 202
    assert replay.status_code == 200
    assert replay.json()["job_id"] == created.json()["job_id"]
    assert created.json()["status_url"].endswith(created.json()["job_id"])
    assert conflict.status_code == 409
    assert (
        await api_client.post("/api/v1/ai/analyses", headers=owner, json=analysis_payload())
    ).status_code == 202
    assert (
        await api_client.post("/api/v1/ai/analyses", headers=owner, json=analysis_payload())
    ).status_code == 202
    assert (
        await api_client.post("/api/v1/ai/analyses", headers=owner, json=analysis_payload())
    ).status_code == 429

    async with session_factory() as session:
        stored = await session.get(AnalysisJob, UUID(created.json()["job_id"]))
        assert stored is not None
        assert payload["text"].encode("utf-8") not in stored.input_ciphertext

    job_url = f"/api/v1/ai/analyses/{created.json()['job_id']}"
    assert (await api_client.get(job_url, headers=other)).status_code == 404
    status_response = await api_client.get(job_url, headers=owner)
    assert status_response.json()["status"] == "queued"
    assert status_response.json()["retryable"] is True
    assert (await api_client.delete(job_url, headers=owner)).status_code == 204
    assert (await api_client.get(job_url, headers=owner)).json()["status"] == "cancelled"
    assert (await api_client.delete(job_url, headers=owner)).status_code == 409


async def test_draft_update_and_confirmation_are_versioned_and_idempotent(
    api_client: AsyncClient,
    session_factory,
) -> None:
    owner = await register(api_client, "draft-owner@example.com")
    other = await register(api_client, "draft-other@example.com")
    job_id, draft_id, entity_id, food = await prepare_draft(api_client, session_factory, owner)

    status_response = await api_client.get(f"/api/v1/ai/analyses/{job_id}", headers=owner)
    assert status_response.json()["draft_id"] == str(draft_id)
    draft_url = f"/api/v1/ai/drafts/{draft_id}"
    assert (await api_client.get(draft_url, headers=other)).status_code == 404
    draft = await api_client.get(draft_url, headers=owner)
    assert draft.json()["entities"][0]["candidates"][0]["name"] == "苹果"

    update = {
        "expected_version": 1,
        "log_date": "2026-09-14",
        "entities": [
            {
                "entity_id": str(entity_id),
                "normalized_name": "苹果",
                "amount": 1.5,
                "unit": "个",
                "meal_type": "lunch",
                "matched_food_id": food["id"],
                "catalog_revision": food["current_revision"],
            }
        ],
    }
    updated = await api_client.put(draft_url, headers=owner, json=update)
    stale = await api_client.put(draft_url, headers=owner, json=update)
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert stale.status_code == 409

    confirmation_id = uuid4()
    log_client_id = uuid4()
    confirmation = {
        "client_confirmation_id": str(confirmation_id),
        "expected_draft_version": 2,
        "entities": [
            {
                "source_entity_id": str(entity_id),
                "client_id": str(log_client_id),
                "food_item_id": food["id"],
                "catalog_revision": food["current_revision"],
                "amount": 2,
                "unit": "个",
                "meal_type": "snack",
            }
        ],
    }
    confirm_url = f"{draft_url}/confirm"
    created = await api_client.post(confirm_url, headers=owner, json=confirmation)
    replay = await api_client.post(confirm_url, headers=owner, json=confirmation)
    assert created.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["confirmation_id"] == created.json()["confirmation_id"]
    assert replay.json()["logs"][0]["id"] == created.json()["logs"][0]["id"]
    assert replay.json()["log_identities"][0] == {
        "entity_id": str(entity_id),
        "client_id": str(log_client_id),
        "log_id": created.json()["logs"][0]["id"],
    }
    assert created.json()["logs"][0]["kcal"] == 208

    logs = await api_client.get(
        "/api/v1/logs",
        headers=owner,
        params={"date_from": "2026-09-14", "date_to": "2026-09-14"},
    )
    assert len(logs.json()) == 1
    assert (await api_client.delete(draft_url, headers=owner)).status_code == 409
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(AnalysisConfirmation)) == 1
        corrections = list(
            (
                await session.scalars(
                    select(AnalysisCorrection).order_by(AnalysisCorrection.field_name)
                )
            ).all()
        )
        assert {item.field_name for item in corrections} == {"amount", "meal_type"}


async def test_confirmation_rolls_back_the_whole_batch_on_catalog_conflict(
    api_client: AsyncClient,
    session_factory,
) -> None:
    owner = await register(api_client, "draft-rollback@example.com")
    _, draft_id, entity_id, food = await prepare_draft(api_client, session_factory, owner)
    request = {
        "client_confirmation_id": str(uuid4()),
        "expected_draft_version": 1,
        "entities": [
            {
                "source_entity_id": str(entity_id),
                "client_id": str(uuid4()),
                "food_item_id": food["id"],
                "catalog_revision": food["current_revision"],
                "amount": 1,
                "unit": "个",
                "meal_type": "lunch",
            },
            {
                "client_id": str(uuid4()),
                "food_item_id": food["id"],
                "catalog_revision": "outdated-revision",
                "amount": 1,
                "unit": "个",
                "meal_type": "snack",
            },
        ],
    }
    response = await api_client.post(
        f"/api/v1/ai/drafts/{draft_id}/confirm", headers=owner, json=request
    )
    assert response.status_code == 409
    invalid_unit = {
        **request,
        "client_confirmation_id": str(uuid4()),
        "entities": [
            {
                **request["entities"][0],
                "client_id": str(uuid4()),
                "unit": "ml",
            }
        ],
    }
    invalid_response = await api_client.post(
        f"/api/v1/ai/drafts/{draft_id}/confirm",
        headers=owner,
        json=invalid_unit,
    )
    assert invalid_response.status_code == 422
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(FoodLog)) == 0
        draft = await session.get(AnalysisDraft, draft_id)
        assert draft is not None and draft.status == "review"


async def test_concurrent_postgres_confirmation_creates_exactly_one_batch(
    pg_session_factory,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_global_catalog(seed_session)
    user_id = uuid4()
    job_id = uuid4()
    draft_id = uuid4()
    entity_id = uuid4()
    async with pg_session_factory() as session:
        food = await session.scalar(
            select(FoodItem).where(
                FoodItem.nutrition_complete.is_(True),
                FoodItem.nutrition_basis_unit == "g",
            )
        )
        assert food is not None
        session.add(
            User(
                id=user_id,
                email=f"analysis-concurrent-{user_id}@example.test",
                password_hash="test-only",
            )
        )
        await session.flush()
        session.add(
            AnalysisJob(
                id=job_id,
                user_id=user_id,
                client_request_id=uuid4(),
                request_hash="a" * 64,
                input_type="text",
                input_ciphertext=b"encrypted-test-only",
                input_key_version=1,
                input_expires_at=datetime.now(UTC) + timedelta(hours=1),
                status="succeeded",
                provider="rule_based_v1",
                model="rule-based-v1",
                prompt_version="rule-food-text-v1.0.0",
                result_schema_version="draft-v1",
                completed_at=datetime.now(UTC),
            )
        )
        await session.flush()
        session.add(
            AnalysisDraft(
                id=draft_id,
                job_id=job_id,
                user_id=user_id,
                status="review",
                version=1,
                log_date=date(2026, 9, 14),
                result_schema_version="draft-v1",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await session.flush()
        session.add(
            AnalysisEntity(
                id=entity_id,
                draft_id=draft_id,
                position=0,
                raw_name=food.name,
                normalized_name=food.name,
                amount=Decimal("100"),
                unit="g",
                meal_type="lunch",
                confidence=Decimal("1"),
                needs_review=False,
                matched_food_id=food.id,
                catalog_revision=food.current_revision,
                candidates=[],
            )
        )
        await session.commit()
        food_id = food.id
        revision = food.current_revision

    confirmation_request = AnalysisConfirmRequest.model_validate(
        {
            "client_confirmation_id": str(uuid4()),
            "expected_draft_version": 1,
            "entities": [
                {
                    "source_entity_id": str(entity_id),
                    "client_id": str(uuid4()),
                    "food_item_id": str(food_id),
                    "catalog_revision": revision,
                    "amount": 100,
                    "unit": "g",
                    "meal_type": "lunch",
                }
            ],
        }
    )

    async def confirm_once():
        async with pg_session_factory() as session:
            return await confirm_analysis_draft(
                session,
                user_id=user_id,
                draft_id=draft_id,
                request=confirmation_request,
            )

    first, second = await asyncio.gather(confirm_once(), confirm_once())
    assert {first[1], second[1]} == {True, False}
    assert first[0].confirmation_id == second[0].confirmation_id
    assert first[0].logs[0].id == second[0].logs[0].id
    async with pg_session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AnalysisConfirmation)
                .where(AnalysisConfirmation.user_id == user_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(FoodLog).where(FoodLog.user_id == user_id)
            )
            == 1
        )
