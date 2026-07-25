from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import User
from app.services.demo_data import seed_demo_account
from app.services.demo_guard import DemoGuard


class FakeRedis:
    def __init__(self, result=(1, 60_000), error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple] = []

    async def eval(self, *args):
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.result


async def test_demo_rate_limit_is_atomic_scoped_and_returns_retry_after() -> None:
    user = User(id=uuid4(), email="demo-guard@example.com", password_hash="unused", is_demo=True)
    allowed_redis = FakeRedis(result=(12, 45_001))
    guard = DemoGuard(Settings(demo_ai_requests_per_window=12), allowed_redis)  # type: ignore[arg-type]

    await guard.enforce_rate(user, "ai")

    assert len(allowed_redis.calls) == 1
    assert str(user.id) in allowed_redis.calls[0][2]
    assert user.email not in allowed_redis.calls[0][2]

    blocked = DemoGuard(  # type: ignore[arg-type]
        Settings(demo_ai_requests_per_window=12),
        FakeRedis(result=(13, 45_001)),
    )
    with pytest.raises(HTTPException) as raised:
        await blocked.enforce_rate(user, "ai")
    assert raised.value.status_code == 429
    assert raised.value.headers == {"Retry-After": "46"}


async def test_demo_rate_limit_has_explicit_redis_failure_policy() -> None:
    user = User(id=uuid4(), email="demo-failure@example.com", password_hash="unused", is_demo=True)
    unavailable = FakeRedis(error=RedisConnectionError("redis unavailable"))

    await DemoGuard(  # type: ignore[arg-type]
        Settings(demo_protection_fail_closed=False),
        unavailable,
    ).enforce_rate(user, "write")

    with pytest.raises(HTTPException) as raised:
        await DemoGuard(  # type: ignore[arg-type]
            Settings(demo_protection_fail_closed=True),
            unavailable,
        ).enforce_rate(user, "write")
    assert raised.value.status_code == 503
    assert raised.value.headers == {"Retry-After": "30"}


async def test_demo_log_quota_counts_real_seed_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        seeded = await seed_demo_account(
            session,
            email="quota-demo@example.com",
            password="quota-demo-password",
            anchor_date=date(2026, 7, 22),
        )
        user = await session.get(User, seeded.user_id)
        assert user is not None
        guard = DemoGuard(Settings(demo_max_logs=58), FakeRedis())  # type: ignore[arg-type]

        with pytest.raises(HTTPException) as raised:
            await guard.enforce_capacity(session, user, "logs")

    assert raised.value.status_code == 403
    assert "logs quota" in raised.value.detail


async def test_normal_user_bypasses_demo_protection() -> None:
    user = User(email="normal@example.com", password_hash="unused", is_demo=False)
    redis = FakeRedis(error=AssertionError("redis should not be called"))
    await DemoGuard(Settings(), redis).enforce_rate(user, "ai")  # type: ignore[arg-type]
    assert redis.calls == []
