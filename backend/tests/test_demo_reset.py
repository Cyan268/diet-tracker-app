from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import FoodLog, User
from app.services.demo_reset import reset_demo_once


class ResetLockRedis:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.set_calls: list[tuple] = []
        self.eval_calls: list[tuple] = []

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return self.acquired

    async def eval(self, *args):
        self.eval_calls.append(args)
        return 1


async def test_automatic_demo_reset_uses_lock_and_rotates_account(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(
        demo_reset_interval_minutes=60,
        demo_reset_password="scheduled-demo-password",
        demo_reset_email="scheduled-demo@example.com",
    )
    redis = ResetLockRedis()

    assert await reset_demo_once(  # type: ignore[arg-type]
        settings,
        redis=redis,
        sessions=session_factory,
        anchor_date=date(2026, 7, 22),
    )
    async with session_factory() as session:
        first_user = await session.scalar(
            select(User).where(User.email == "scheduled-demo@example.com")
        )
        first_log_count = await session.scalar(select(func.count()).select_from(FoodLog))
    assert first_user is not None
    first_user_id = first_user.id
    assert first_log_count == 58

    assert await reset_demo_once(  # type: ignore[arg-type]
        settings,
        redis=redis,
        sessions=session_factory,
        anchor_date=date(2026, 7, 23),
    )
    async with session_factory() as session:
        second_user = await session.scalar(
            select(User).where(User.email == "scheduled-demo@example.com")
        )
        second_log_count = await session.scalar(select(func.count()).select_from(FoodLog))

    assert second_user is not None and second_user.id != first_user_id
    assert second_log_count == 58
    assert len(redis.set_calls) == 2
    assert len(redis.eval_calls) == 2


async def test_automatic_demo_reset_skips_when_another_instance_holds_lock(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(
        demo_reset_interval_minutes=60,
        demo_reset_password="scheduled-demo-password",
    )
    redis = ResetLockRedis(acquired=False)

    assert not await reset_demo_once(  # type: ignore[arg-type]
        settings,
        redis=redis,
        sessions=session_factory,
        anchor_date=date(2026, 7, 22),
    )
    async with session_factory() as session:
        user_count = await session.scalar(select(func.count()).select_from(User))
    assert user_count == 0
    assert redis.eval_calls == []
