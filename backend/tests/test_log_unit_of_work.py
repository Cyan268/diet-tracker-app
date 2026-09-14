from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models import FoodLog, SyncChange, User, UserSyncState
from app.schemas.diet import LogContent, LogCreateRequest
from app.services.diet import (
    ResourceNotFoundError,
    create_log,
    create_log_in_transaction,
    delete_log_in_transaction,
    replace_log_in_transaction,
)


def request(*, client_id: UUID | None = None, food_item_id: UUID | None = None):
    values: dict[str, object] = {
        "client_id": str(client_id or uuid4()),
        "log_date": "2026-09-07",
        "meal_type": "lunch",
        "amount": 1,
        "unit": "serving",
    }
    if food_item_id is None:
        values.update(
            {
                "custom_name": "transaction test",
                "nutrition": {
                    "kcal": 100,
                    "protein": 10,
                    "fat": 3,
                    "carbs": 20,
                    "sugar": 1,
                    "sodium": 20,
                    "caffeine": 0,
                },
            }
        )
    else:
        values["food_item_id"] = str(food_item_id)
    return LogCreateRequest.model_validate(values)


@pytest.fixture
async def owner(session_factory):
    owner_id = uuid4()
    async with session_factory() as session:
        session.add(
            User(
                id=owner_id,
                email=f"u2-unit-{owner_id}@example.test",
                password_hash="test-only",
            )
        )
        await session.commit()
    return owner_id


async def test_internal_create_never_commits_or_rolls_back(session_factory, owner) -> None:
    async with session_factory() as session:
        commit = AsyncMock(side_effect=AssertionError("internal function committed"))
        rollback = AsyncMock(side_effect=AssertionError("internal function rolled back"))
        session.commit = commit
        session.rollback = rollback

        log, created = await create_log_in_transaction(session, owner, request())

        assert created is True
        assert log.user_id == owner
        assert await session.scalar(select(func.count(FoodLog.id))) == 1
        assert await session.scalar(select(func.count(SyncChange.id))) == 1
        commit.assert_not_awaited()
        rollback.assert_not_awaited()

    async with session_factory() as reader:
        assert await reader.scalar(select(func.count(FoodLog.id))) == 0
        assert await reader.scalar(select(func.count(SyncChange.id))) == 0
        assert await reader.get(UserSyncState, owner) is None


async def test_outer_rollback_removes_entire_batch_when_later_write_fails(
    session_factory,
    owner,
) -> None:
    async with session_factory() as session:
        with pytest.raises(ResourceNotFoundError):
            await create_log_in_transaction(session, owner, request())
            await create_log_in_transaction(
                session,
                owner,
                request(food_item_id=uuid4()),
            )
        await session.rollback()

    async with session_factory() as reader:
        assert await reader.scalar(select(func.count(FoodLog.id))) == 0
        assert await reader.scalar(select(func.count(SyncChange.id))) == 0
        assert await reader.get(UserSyncState, owner) is None


async def test_internal_replace_never_ends_transaction(session_factory, owner) -> None:
    original_request = request()
    async with session_factory() as session:
        original, _ = await create_log(session, owner, original_request)
        original_id = original.id

    replacement_request = request()
    replacement = LogContent.model_validate(replacement_request.model_dump(exclude={"client_id"}))
    async with session_factory() as session:
        commit = AsyncMock(side_effect=AssertionError("internal function committed"))
        rollback = AsyncMock(side_effect=AssertionError("internal function rolled back"))
        session.commit = commit
        session.rollback = rollback

        updated = await replace_log_in_transaction(session, owner, original_id, 1, replacement)

        assert updated.version == 2
        commit.assert_not_awaited()
        rollback.assert_not_awaited()

    async with session_factory() as reader:
        persisted = await reader.get(FoodLog, original_id)
        assert persisted is not None
        assert persisted.version == 1
        assert persisted.custom_name == original_request.custom_name
        assert await reader.scalar(select(func.count(SyncChange.id))) == 1


async def test_internal_delete_never_ends_transaction(session_factory, owner) -> None:
    async with session_factory() as session:
        original, _ = await create_log(session, owner, request())
        original_id = original.id

    async with session_factory() as session:
        commit = AsyncMock(side_effect=AssertionError("internal function committed"))
        rollback = AsyncMock(side_effect=AssertionError("internal function rolled back"))
        session.commit = commit
        session.rollback = rollback

        await delete_log_in_transaction(session, owner, original_id, 1)

        assert await session.get(FoodLog, original_id) is None
        commit.assert_not_awaited()
        rollback.assert_not_awaited()

    async with session_factory() as reader:
        persisted = await reader.get(FoodLog, original_id)
        assert persisted is not None
        assert persisted.version == 1
        assert await reader.scalar(select(func.count(SyncChange.id))) == 1
