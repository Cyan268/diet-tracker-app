import asyncio
from copy import deepcopy
from uuid import uuid4

from httpx2 import AsyncClient


async def register(client: AsyncClient, prefix: str) -> dict[str, object]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{prefix}-{uuid4().hex}@example.com",
            "password": "correct-horse-123",
        },
    )
    assert response.status_code == 201
    return response.json()


def custom_log(client_id: str | None = None) -> dict[str, object]:
    return {
        "client_id": client_id or str(uuid4()),
        "log_date": "2026-07-17",
        "meal_type": "breakfast",
        "custom_name": "PostgreSQL concurrency meal",
        "amount": 1,
        "unit": "serving",
        "nutrition": {
            "kcal": 120,
            "protein": 10,
            "fat": 5,
            "carbs": 20,
            "sugar": 2,
            "sodium": 300,
            "caffeine": 0,
        },
        "note": "concurrency test",
    }


def bearer(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def test_concurrent_idempotent_create_returns_one_resource(
    pg_api_client: AsyncClient,
) -> None:
    client = pg_api_client
    auth = await register(client, "idempotency-race")
    payload = custom_log()

    first, second = await asyncio.gather(
        client.post("/api/v1/logs", headers=bearer(auth), json=payload),
        client.post("/api/v1/logs", headers=bearer(auth), json=payload),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 201]
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["client_id"] == payload["client_id"]


async def test_concurrent_update_allows_only_one_expected_version(
    pg_api_client: AsyncClient,
) -> None:
    client = pg_api_client
    auth = await register(client, "optimistic-race")
    created = (await client.post("/api/v1/logs", headers=bearer(auth), json=custom_log())).json()
    first_payload = custom_log()
    first_payload.pop("client_id")
    first_payload["expected_version"] = 1
    first_payload["note"] = "writer one"
    second_payload = deepcopy(first_payload)
    second_payload["note"] = "writer two"

    first, second = await asyncio.gather(
        client.put(
            f"/api/v1/logs/{created['id']}",
            headers=bearer(auth),
            json=first_payload,
        ),
        client.put(
            f"/api/v1/logs/{created['id']}",
            headers=bearer(auth),
            json=second_payload,
        ),
    )
    current = await client.get(f"/api/v1/logs/{created['id']}", headers=bearer(auth))

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert current.status_code == 200
    assert current.json()["version"] == 2
    assert current.json()["note"] in {"writer one", "writer two"}


async def test_concurrent_refresh_detects_replay_and_revokes_token_family(
    pg_api_client: AsyncClient,
) -> None:
    client = pg_api_client
    auth = await register(client, "refresh-race")
    refresh_body = {"refresh_token": auth["refresh_token"]}

    first, second = await asyncio.gather(
        client.post("/api/v1/auth/refresh", json=refresh_body),
        client.post("/api/v1/auth/refresh", json=refresh_body),
    )
    winner = first if first.status_code == 200 else second
    family_retry = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": winner.json()["refresh_token"]},
    )

    assert sorted([first.status_code, second.status_code]) == [200, 401]
    assert family_retry.status_code == 401
