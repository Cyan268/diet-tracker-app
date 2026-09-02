"""Shared write ordering: lock before changing any log, release only on commit/rollback."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodLog, SyncChange, UserSyncState
from app.schemas.diet import LogResponse


async def lock_user_sync_state(session: AsyncSession, user_id: UUID) -> UserSyncState:
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    await session.execute(
        insert(UserSyncState)
        .values(user_id=user_id, epoch=uuid4(), last_seq=0, minimum_valid_after=0)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    # populate_existing prevents a previously read ORM object from supplying a stale counter.
    return (
        await session.execute(
            select(UserSyncState)
            .where(UserSyncState.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


def record_log_change(
    session: AsyncSession, state: UserSyncState, log: FoodLog, operation: str
) -> None:
    if state.user_id != log.user_id:
        raise ValueError("sync state owner does not match log owner")
    state.last_seq += 1
    session.add(
        SyncChange(
            user_id=log.user_id,
            user_seq=state.last_seq,
            aggregate_id=log.id,
            client_id=log.client_id,
            operation=operation,
            version=log.version,
            payload=(
                LogResponse.model_validate(log).model_dump(mode="json")
                if operation == "upsert"
                else None
            ),
        )
    )
