from fastapi import Request
from httpx2 import AsyncClient

from app.api.dependencies import get_auth_guard
from app.main import app


class RecordingAuthGuard:
    def __init__(self) -> None:
        self.rate_calls: list[tuple[str, str, str]] = []
        self.clear_calls: list[str] = []

    async def enforce_rate(self, action: str, email: str, request: Request) -> None:
        self.rate_calls.append((action, email, request.scope["type"]))

    async def clear_login_rate(self, email: str) -> None:
        self.clear_calls.append(email)


async def test_auth_routes_apply_rate_policy_and_clear_only_after_success(
    api_client: AsyncClient,
) -> None:
    guard = RecordingAuthGuard()
    app.dependency_overrides[get_auth_guard] = lambda: guard
    payload = {"email": "Guard@Example.com", "password": "correct-horse-123"}

    registered = await api_client.post("/api/v1/auth/register", json=payload)
    failed = await api_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "wrong-password"},
    )
    logged_in = await api_client.post("/api/v1/auth/login", json=payload)

    assert registered.status_code == 201
    assert failed.status_code == 401
    assert logged_in.status_code == 200
    assert guard.rate_calls == [
        ("register", "Guard@example.com", "http"),
        ("login", "Guard@example.com", "http"),
        ("login", "Guard@example.com", "http"),
    ]
    assert guard.clear_calls == ["Guard@example.com"]
