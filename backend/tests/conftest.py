import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_auth_guard, get_demo_guard
from app.core.database import get_session
from app.main import app
from app.models import Base


def pytest_asyncio_loop_factories():
    # Explicit factories avoid deprecated policy overrides and support Psycopg on Windows.
    return {"selector": asyncio.SelectorEventLoop}


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


@pytest.fixture
async def pg_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    raw = os.getenv("NUTRIPILOT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("NUTRIPILOT_TEST_DATABASE_URL is required for isolated PostgreSQL tests")
    url = make_url(raw)
    if url.host not in {"127.0.0.1", "localhost", "::1"} or url.database != "nutripilot_u4_test":
        pytest.fail("PostgreSQL tests refuse non-loopback hosts or a non-test database name")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            assert (await connection.scalar(text("SELECT version()"))).startswith("PostgreSQL")
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "20260831_0009"
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def pg_api_client(pg_session_factory) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with pg_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_demo_guard] = lambda: NoopDemoGuard()
    app.dependency_overrides[get_auth_guard] = lambda: NoopAuthGuard()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
