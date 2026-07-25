from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli.seed_demo import validate_seed_environment
from app.models import FoodItem, FoodLog, SyncChange, User, UserProfile
from app.services.demo_data import (
    DemoAccountConflictError,
    DemoResetRequiredError,
    seed_demo_account,
)
from app.services.weekly_report import build_weekly_report_facts


async def test_demo_seed_creates_complete_two_week_story_and_resets_atomically(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    anchor = date(2026, 7, 22)
    async with session_factory() as session:
        first = await seed_demo_account(
            session,
            email="Demo@NutriPilot.Example",
            password="first-demo-password",
            anchor_date=anchor,
        )
        user = await session.get(User, first.user_id)
        profile = await session.get(UserProfile, first.user_id)
        facts = await build_weekly_report_facts(session, first.user_id, anchor)
        log_count = await session.scalar(
            select(func.count()).select_from(FoodLog).where(FoodLog.user_id == first.user_id)
        )
        food_count = await session.scalar(
            select(func.count())
            .select_from(FoodItem)
            .where(FoodItem.owner_user_id == first.user_id)
        )
        sync_count = await session.scalar(
            select(func.count()).select_from(SyncChange).where(SyncChange.user_id == first.user_id)
        )

        assert user is not None and user.is_demo is True
        assert user.email == "demo@nutripilot.example"
        assert profile is not None and profile.goal == "maintain"
        assert first.log_count == 58
        assert log_count == 58
        assert food_count == first.private_food_count == 2
        assert sync_count == 58
        assert facts.current.days_with_records == 7
        assert facts.previous.days_with_records == 7
        assert facts.comparison_available is True
        assert facts.targets is not None

        with pytest.raises(DemoResetRequiredError):
            await seed_demo_account(
                session,
                email=first.email,
                password="second-demo-password",
                anchor_date=anchor,
            )

        reset = await seed_demo_account(
            session,
            email=first.email,
            password="second-demo-password",
            anchor_date=anchor,
            reset_existing=True,
        )
        reset_log_count = await session.scalar(
            select(func.count()).select_from(FoodLog).where(FoodLog.user_id == reset.user_id)
        )
        all_demo_users = list(
            (await session.scalars(select(User).where(User.email == first.email))).all()
        )

    assert reset.reset is True
    assert reset.user_id != first.user_id
    assert reset_log_count == 58
    assert len(all_demo_users) == 1


async def test_demo_seed_refuses_to_replace_normal_account(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(User(email="owner@example.com", password_hash="not-used", is_demo=False))
        await session.commit()

        with pytest.raises(DemoAccountConflictError):
            await seed_demo_account(
                session,
                email="owner@example.com",
                password="demo-password-123",
                anchor_date=date(2026, 7, 22),
                reset_existing=True,
            )


def test_production_demo_seed_requires_explicit_opt_in() -> None:
    with pytest.raises(RuntimeError, match="--allow-production"):
        validate_seed_environment("production", allow_production=False)
    validate_seed_environment("production", allow_production=True)
    validate_seed_environment("development", allow_production=False)
