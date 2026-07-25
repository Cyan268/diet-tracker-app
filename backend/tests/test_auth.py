from httpx2 import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.security import digest_refresh_token
from app.main import app
from app.models import RefreshToken

REGISTER_PAYLOAD = {"email": "Student@Example.com", "password": "correct-horse-123"}


async def register(api_client: AsyncClient) -> dict[str, object]:
    response = await api_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    return response.json()


async def test_register_normalizes_email_and_returns_tokens(api_client: AsyncClient) -> None:
    body = await register(api_client)

    assert body["user"]["email"] == "student@example.com"
    assert body["user"]["is_demo"] is False
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]
    assert body["refresh_token"]


async def test_duplicate_email_is_rejected_case_insensitively(api_client: AsyncClient) -> None:
    await register(api_client)

    response = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "STUDENT@example.com", "password": "another-password"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "email already registered"}


async def test_login_rejects_wrong_password_without_leaking_account_state(
    api_client: AsyncClient,
) -> None:
    await register(api_client)

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid email or password"}


async def test_login_returns_new_token_pair(api_client: AsyncClient) -> None:
    registered = await register(api_client)

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "STUDENT@example.com", "password": REGISTER_PAYLOAD["password"]},
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != registered["refresh_token"]


async def test_current_user_requires_valid_access_token(api_client: AsyncClient) -> None:
    body = await register(api_client)

    unauthorized = await api_client.get("/api/v1/users/me")
    authorized = await api_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )

    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"
    assert authorized.status_code == 200
    assert authorized.json()["email"] == "student@example.com"


async def test_refresh_rotation_detects_replay_and_revokes_token_family(
    api_client: AsyncClient,
) -> None:
    registered = await register(api_client)
    original = registered["refresh_token"]

    rotated = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original},
    )
    assert rotated.status_code == 200
    replacement = rotated.json()["refresh_token"]
    assert replacement != original

    replay = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original},
    )
    family_token = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": replacement},
    )

    assert replay.status_code == 401
    assert family_token.status_code == 401


async def test_logout_is_idempotent_and_revokes_refresh_token(api_client: AsyncClient) -> None:
    body = await register(api_client)
    payload = {"refresh_token": body["refresh_token"]}

    first = await api_client.post("/api/v1/auth/logout", json=payload)
    second = await api_client.post("/api/v1/auth/logout", json=payload)
    refresh = await api_client.post("/api/v1/auth/refresh", json=payload)

    assert first.status_code == 204
    assert second.status_code == 204
    assert refresh.status_code == 401


async def test_database_stores_only_refresh_token_digest(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    body = await register(api_client)
    raw_token = body["refresh_token"]

    async with session_factory() as session:
        stored = await session.scalar(select(RefreshToken))

    assert stored is not None
    assert stored.token_hash == digest_refresh_token(raw_token)
    assert raw_token != stored.token_hash


async def test_public_runtime_config_exposes_only_registration_policy(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/meta/config")

    assert response.status_code == 200
    assert response.json() == {"registration_enabled": True}


async def test_disabled_public_registration_is_enforced_by_backend(
    api_client: AsyncClient,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        public_registration_enabled=False,
    )

    config = await api_client.get("/api/v1/meta/config")
    response = await api_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

    assert config.json() == {"registration_enabled": False}
    assert response.status_code == 403
    assert response.json() == {"detail": "public registration is disabled"}
