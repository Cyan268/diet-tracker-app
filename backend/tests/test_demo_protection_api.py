from datetime import date

from httpx2 import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import get_demo_guard
from app.main import app
from app.services.demo_data import seed_demo_account


class RecordingDemoGuard:
    def __init__(self) -> None:
        self.rates: list[str] = []
        self.quotas: list[str] = []

    async def enforce_rate(self, _user, action: str) -> None:
        self.rates.append(action)

    async def enforce_capacity(self, _session, _user, resource: str, **_kwargs) -> None:
        self.quotas.append(resource)


async def test_demo_mutation_and_ai_routes_use_protection_dependency(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await seed_demo_account(
            session,
            email="protected-demo@example.com",
            password="protected-demo-password",
            anchor_date=date(2026, 7, 22),
        )
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "protected-demo@example.com", "password": "protected-demo-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    guard = RecordingDemoGuard()
    app.dependency_overrides[get_demo_guard] = lambda: guard

    conversation = await api_client.post(
        "/api/v1/ai/assistant/conversations",
        headers=headers,
        json={"title": "限流验收"},
    )
    report = await api_client.post(
        "/api/v1/ai/reports/weekly:generate",
        headers=headers,
        json={"end_date": "2026-07-22", "locale": "zh-CN"},
    )

    assert conversation.status_code == 201
    assert report.status_code == 200
    assert guard.rates == ["write", "ai"]
    assert guard.quotas == ["conversations"]
