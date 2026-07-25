from collections.abc import AsyncIterator

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_auth_guard, get_demo_guard
from app.core.database import get_session
from app.main import app
from app.models import Base


class NoopDemoGuard:
    async def enforce_rate(self, *_args, **_kwargs) -> None:
        return None

    async def enforce_capacity(self, *_args, **_kwargs) -> None:
        return None


class NoopAuthGuard:
    async def enforce_rate(self, *_args, **_kwargs) -> None:
        return None

    async def clear_login_rate(self, *_args, **_kwargs) -> None:
        return None


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield factory

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_demo_guard] = lambda: NoopDemoGuard()
    app.dependency_overrides[get_auth_guard] = lambda: NoopAuthGuard()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
