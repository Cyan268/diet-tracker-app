from copy import deepcopy
from uuid import uuid4

from httpx2 import AsyncClient

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
    "brand": "Test Brand",
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


async def register(client: AsyncClient, email: str = "diet@example.com") -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def custom_log(client_id: str | None = None, kcal: float = 120) -> dict[str, object]:
    return {
        "client_id": client_id or str(uuid4()),
        "log_date": "2026-07-15",
        "meal_type": "breakfast",
        "custom_name": "自制三明治",
        "amount": 1,
        "unit": "份",
        "nutrition": {
            "kcal": kcal,
            "protein": 10,
            "fat": 5,
            "carbs": 20,
            "sugar": 2,
            "sodium": 300,
            "caffeine": 0,
        },
        "note": "早餐",
    }


async def test_profile_upsert_returns_server_calculated_targets(api_client: AsyncClient) -> None:
    headers = await register(api_client)

    missing = await api_client.get("/api/v1/users/me/profile", headers=headers)
    created = await api_client.put("/api/v1/users/me/profile", headers=headers, json=PROFILE)
    fetched = await api_client.get("/api/v1/users/me/profile", headers=headers)

    assert missing.status_code == 404
    assert created.status_code == 200
    assert created.json()["daily_targets"] == {
        "kcal": 2594,
        "protein": 112,
        "fat": 72,
        "carbs": 375,
        "sugar": 50,
        "sodium": 2300,
        "caffeine": 400,
    }
    assert fetched.json()["weight_kg"] == 70


async def test_custom_food_is_visible_only_to_its_owner(api_client: AsyncClient) -> None:
    owner_headers = await register(api_client, "owner@example.com")
    created = await api_client.post("/api/v1/foods", headers=owner_headers, json=FOOD)
    assert created.status_code == 201

    owner_results = await api_client.get(
        "/api/v1/foods",
        headers=owner_headers,
        params={"query": "燕麦"},
    )
    other_headers = await register(api_client, "other@example.com")
    other_results = await api_client.get(
        "/api/v1/foods",
        headers=other_headers,
        params={"query": "燕麦"},
    )

    assert len(owner_results.json()) == 1
    assert other_results.json() == []


async def test_catalog_food_nutrition_is_calculated_by_server(api_client: AsyncClient) -> None:
    headers = await register(api_client)
    food = (await api_client.post("/api/v1/foods", headers=headers, json=FOOD)).json()
    payload = {
        "client_id": str(uuid4()),
        "log_date": "2026-07-15",
        "meal_type": "breakfast",
        "food_item_id": food["id"],
        "amount": 150,
        "unit": "g",
        "note": None,
    }

    response = await api_client.post("/api/v1/logs", headers=headers, json=payload)

    assert response.status_code == 201
    assert response.json()["kcal"] == 570
    assert response.json()["protein"] == 19.5


async def test_log_create_is_idempotent_and_rejects_key_reuse(api_client: AsyncClient) -> None:
    headers = await register(api_client)
    payload = custom_log()

    created = await api_client.post("/api/v1/logs", headers=headers, json=payload)
    replay = await api_client.post("/api/v1/logs", headers=headers, json=payload)
    changed_payload = deepcopy(payload)
    changed_payload["amount"] = 2
    conflict = await api_client.post("/api/v1/logs", headers=headers, json=changed_payload)

    assert created.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert conflict.status_code == 409


async def test_log_update_uses_optimistic_version(api_client: AsyncClient) -> None:
    headers = await register(api_client)
    created = (await api_client.post("/api/v1/logs", headers=headers, json=custom_log())).json()
    update_payload = custom_log()
    update_payload.pop("client_id")
    update_payload["expected_version"] = 1
    update_payload["note"] = "updated"

    updated = await api_client.put(
        f"/api/v1/logs/{created['id']}",
        headers=headers,
        json=update_payload,
    )
    stale = await api_client.put(
        f"/api/v1/logs/{created['id']}",
        headers=headers,
        json=update_payload,
    )

    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["note"] == "updated"
    assert stale.status_code == 409


async def test_logs_are_isolated_between_users(api_client: AsyncClient) -> None:
    owner_headers = await register(api_client, "owner@example.com")
    created = (
        await api_client.post("/api/v1/logs", headers=owner_headers, json=custom_log())
    ).json()
    other_headers = await register(api_client, "other@example.com")

    direct = await api_client.get(f"/api/v1/logs/{created['id']}", headers=other_headers)
    listing = await api_client.get(
        "/api/v1/logs",
        headers=other_headers,
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )

    assert direct.status_code == 404
    assert listing.json() == []


async def test_daily_summary_aggregates_only_current_user(api_client: AsyncClient) -> None:
    headers = await register(api_client, "summary@example.com")
    breakfast = custom_log(kcal=120)
    lunch = custom_log(kcal=280)
    lunch["meal_type"] = "lunch"
    await api_client.post("/api/v1/logs", headers=headers, json=breakfast)
    await api_client.post("/api/v1/logs", headers=headers, json=lunch)

    other_headers = await register(api_client, "other@example.com")
    await api_client.post("/api/v1/logs", headers=other_headers, json=custom_log(kcal=999))
    response = await api_client.get(
        "/api/v1/stats/daily",
        headers=headers,
        params={"summary_date": "2026-07-15"},
    )

    assert response.status_code == 200
    assert response.json()["total_kcal"] == 400
    assert response.json()["meal_breakdown"]["breakfast"] == 120
    assert response.json()["meal_breakdown"]["lunch"] == 280


async def test_delete_requires_current_version(api_client: AsyncClient) -> None:
    headers = await register(api_client)
    created = (await api_client.post("/api/v1/logs", headers=headers, json=custom_log())).json()
    url = f"/api/v1/logs/{created['id']}"

    stale = await api_client.delete(url, headers=headers, params={"expected_version": 2})
    deleted = await api_client.delete(url, headers=headers, params={"expected_version": 1})
    missing = await api_client.get(url, headers=headers)

    assert stale.status_code == 409
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_sync_changes_are_cursor_paginated_and_user_scoped(
    api_client: AsyncClient,
) -> None:
    headers = await register(api_client, "sync-owner@example.com")
    created = (await api_client.post("/api/v1/logs", headers=headers, json=custom_log())).json()
    update_payload = custom_log()
    update_payload.pop("client_id")
    update_payload["expected_version"] = 1
    update_payload["note"] = "changed on another device"
    await api_client.put(
        f"/api/v1/logs/{created['id']}",
        headers=headers,
        json=update_payload,
    )

    first_page = await api_client.get(
        "/api/v1/sync/changes",
        headers=headers,
        params={"after": 0, "limit": 1},
    )
    first_body = first_page.json()

    assert first_page.status_code == 200
    assert first_body["has_more"] is True
    assert first_body["changes"][0]["operation"] == "upsert"
    assert first_body["changes"][0]["log"]["version"] == 1

    second_page = await api_client.get(
        "/api/v1/sync/changes",
        headers=headers,
        params={"after": first_body["next_cursor"], "limit": 10},
    )
    assert second_page.json()["changes"][0]["log"]["version"] == 2

    other_headers = await register(api_client, "sync-other@example.com")
    other_page = await api_client.get(
        "/api/v1/sync/changes",
        headers=other_headers,
        params={"after": 0},
    )
    assert other_page.json()["changes"] == []


async def test_sync_changes_keep_delete_tombstone(api_client: AsyncClient) -> None:
    headers = await register(api_client, "tombstone@example.com")
    created = (await api_client.post("/api/v1/logs", headers=headers, json=custom_log())).json()
    created_page = (
        await api_client.get(
            "/api/v1/sync/changes",
            headers=headers,
            params={"after": 0},
        )
    ).json()

    deleted = await api_client.delete(
        f"/api/v1/logs/{created['id']}",
        headers=headers,
        params={"expected_version": 1},
    )
    tombstone_page = await api_client.get(
        "/api/v1/sync/changes",
        headers=headers,
        params={"after": created_page["next_cursor"]},
    )
    tombstone = tombstone_page.json()["changes"][0]

    assert deleted.status_code == 204
    assert tombstone["operation"] == "delete"
    assert tombstone["server_id"] == created["id"]
    assert tombstone["client_id"] == created["client_id"]
    assert tombstone["log"] is None
