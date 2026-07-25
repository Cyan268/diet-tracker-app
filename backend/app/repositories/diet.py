from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodItem, FoodLog, SyncChange, UserProfile


async def get_profile(session: AsyncSession, user_id: UUID) -> UserProfile | None:
    return await session.get(UserProfile, user_id)


async def get_visible_food(
    session: AsyncSession,
    food_id: UUID,
    user_id: UUID,
) -> FoodItem | None:
    return await session.scalar(
        select(FoodItem).where(
            FoodItem.id == food_id,
            or_(FoodItem.owner_user_id.is_(None), FoodItem.owner_user_id == user_id),
        )
    )


async def search_visible_foods(
    session: AsyncSession,
    user_id: UUID,
    query: str,
    limit: int,
) -> list[FoodItem]:
    statement = select(FoodItem).where(
        or_(FoodItem.owner_user_id.is_(None), FoodItem.owner_user_id == user_id)
    )
    if query:
        statement = statement.where(FoodItem.name.ilike(f"%{query}%"))
    statement = statement.order_by(FoodItem.name, FoodItem.id).limit(limit)
    return list((await session.scalars(statement)).all())


async def get_log(
    session: AsyncSession,
    log_id: UUID,
    user_id: UUID,
) -> FoodLog | None:
    return await session.scalar(
        select(FoodLog).where(FoodLog.id == log_id, FoodLog.user_id == user_id)
    )


async def get_log_by_client_id(
    session: AsyncSession,
    user_id: UUID,
    client_id: UUID,
) -> FoodLog | None:
    return await session.scalar(
        select(FoodLog).where(
            FoodLog.user_id == user_id,
            FoodLog.client_id == client_id,
        )
    )


async def list_logs(
    session: AsyncSession,
    user_id: UUID,
    date_from: date,
    date_to: date,
    limit: int,
    offset: int,
) -> list[FoodLog]:
    statement = (
        select(FoodLog)
        .where(
            FoodLog.user_id == user_id,
            FoodLog.log_date >= date_from,
            FoodLog.log_date <= date_to,
        )
        .order_by(FoodLog.log_date.desc(), FoodLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.scalars(statement)).all())


async def list_sync_changes(
    session: AsyncSession,
    user_id: UUID,
    after: int,
    limit: int,
) -> list[SyncChange]:
    statement = (
        select(SyncChange)
        .where(SyncChange.user_id == user_id, SyncChange.id > after)
        .order_by(SyncChange.id)
        .limit(limit)
    )
    return list((await session.scalars(statement)).all())
