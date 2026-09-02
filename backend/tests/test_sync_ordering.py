import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.models import FoodLog, SyncChange, User, UserSyncState
from app.schemas.diet import LogContent, LogCreateRequest
from app.services.diet import create_log, delete_log, replace_log
from app.services.log_changes import lock_user_sync_state, record_log_change


def request():
    return LogCreateRequest.model_validate(
        {
            "client_id": str(uuid4()),
            "log_date": "2026-08-31",
            "meal_type": "lunch",
            "custom_name": "isolated sync test",
            "amount": 1,
            "unit": "serving",
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


@pytest.fixture
async def pg_owner(pg_session_factory):
    owner = uuid4()
    async with pg_session_factory() as session:
        session.add(User(id=owner, email=f"u4-{owner}@example.test", password_hash="test-only"))
        await session.commit()
    try:
        yield owner
    finally:
        async with pg_session_factory() as session:
            await session.execute(delete(User).where(User.id == owner))
            await session.commit()


async def test_reproduces_sequence_allocation_not_commit_order(pg_session_factory, pg_owner):
    """Intentional bypass of the new writer, reproducing the OLD algorithm's failure."""

    def event(seq):
        return SyncChange(
            user_id=pg_owner,
            user_seq=seq,
            aggregate_id=uuid4(),
            client_id=uuid4(),
            operation="delete",
            version=1,
            payload=None,
        )

    async with pg_session_factory() as first, pg_session_factory() as second:
        early = event(1)
        first.add(early)
        await first.flush()  # Allocates the smaller global ID, but does not commit.
        later = event(2)
        second.add(later)
        await second.commit()
        assert early.id < later.id
        async with pg_session_factory() as reader:
            seen = (
                await reader.scalars(select(SyncChange).where(SyncChange.user_id == pg_owner))
            ).all()
            assert [change.id for change in seen] == [later.id]
        await first.commit()
        async with pg_session_factory() as reader:
            missed = (
                await reader.scalars(
                    select(SyncChange).where(
                        SyncChange.user_id == pg_owner, SyncChange.id > later.id
                    )
                )
            ).all()
            assert missed == []  # The early event exists but is permanently below the old cursor.
            assert await reader.get(SyncChange, early.id) is not None


async def test_same_owner_blocks_before_log_write_and_other_owner_progresses(
    pg_session_factory, pg_owner
):
    started = asyncio.Event()

    async def second_writer():
        async with pg_session_factory() as session:
            started.set()
            return await create_log(session, pg_owner, request())

    async with pg_session_factory() as first:
        state = await lock_user_sync_state(first, pg_owner)
        payload = request()
        log = FoodLog(
            user_id=pg_owner,
            payload_hash="test",
            **payload.model_dump(exclude={"nutrition"}),
            **payload.nutrition.model_dump(),
        )
        first.add(log)
        await first.flush()
        record_log_change(first, state, log, "upsert")
        await first.flush()
        contender = asyncio.create_task(second_writer())
        try:
            await started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(contender), timeout=0.15)
            # A completely different owner is not serialized behind this user's lock.
            async with pg_session_factory() as other:
                user = User(id=uuid4(), email=f"other-{uuid4()}@example.test", password_hash="test")
                other.add(user)
                await other.commit()
                await asyncio.wait_for(create_log(other, user.id, request()), timeout=5)
            await first.commit()
            await asyncio.wait_for(contender, timeout=5)
        finally:
            if not contender.done():
                contender.cancel()
                await asyncio.gather(contender, return_exceptions=True)
    async with pg_session_factory() as reader:
        events = (
            await reader.scalars(
                select(SyncChange).where(SyncChange.user_id == pg_owner).order_by(SyncChange.id)
            )
        ).all()
        assert [event.user_seq for event in events] == [1, 2]
        assert (await reader.get(UserSyncState, pg_owner)).last_seq == 2


async def test_rollback_does_not_publish_a_counter_or_event(pg_session_factory, pg_owner):
    async with pg_session_factory() as session:
        state = await lock_user_sync_state(session, pg_owner)
        state.last_seq = 9
        await session.flush()
        await session.rollback()
        await create_log(session, pg_owner, request())
    async with pg_session_factory() as reader:
        assert (await reader.get(UserSyncState, pg_owner)).last_seq == 1
        assert (
            await reader.scalars(select(SyncChange.user_seq).where(SyncChange.user_id == pg_owner))
        ).all() == [1]


async def test_concurrent_initialization_and_idempotency_use_one_sequence(
    pg_session_factory, pg_owner
):
    payload = request()

    async def write():
        async with pg_session_factory() as session:
            return await create_log(session, pg_owner, payload)

    results = await asyncio.gather(write(), write())
    assert sorted(created for _, created in results) == [False, True]
    assert results[0][0].id == results[1][0].id
    async with pg_session_factory() as reader:
        assert (await reader.get(UserSyncState, pg_owner)).last_seq == 1
        assert (
            len(
                (
                    await reader.scalars(select(SyncChange).where(SyncChange.user_id == pg_owner))
                ).all()
            )
            == 1
        )


async def test_create_update_delete_all_record_ordered_events(pg_session_factory, pg_owner):
    payload = request()
    async with pg_session_factory() as session:
        log, _ = await create_log(session, pg_owner, payload)
        content = LogContent.model_validate(
            {**payload.model_dump(exclude={"client_id"}), "note": "edited"}
        )
        log = await replace_log(session, pg_owner, log.id, 1, content)
        await delete_log(session, pg_owner, log.id, 2)
    async with pg_session_factory() as reader:
        events = (
            await reader.scalars(
                select(SyncChange)
                .where(SyncChange.user_id == pg_owner)
                .order_by(SyncChange.user_seq)
            )
        ).all()
        assert [item.user_seq for item in events] == [1, 2, 3]
        assert [item.operation for item in events] == ["upsert", "upsert", "delete"]
        assert events[0].id < events[1].id < events[2].id
