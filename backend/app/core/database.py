from collections.abc import AsyncIterator
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.runtime_metrics import record_safely, runtime_metrics

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
)
session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        started_at = perf_counter()
        await session.connection()
        record_safely(
            runtime_metrics.record_db_pool_wait,
            round((perf_counter() - started_at) * 1000),
        )
        yield session


async def get_write_session() -> AsyncIterator[AsyncSession]:
    """Yield a session whose transaction is owned only by one write service."""

    async with session_factory() as session:
        started_at = perf_counter()
        await session.connection()
        record_safely(
            runtime_metrics.record_db_pool_wait,
            round((perf_counter() - started_at) * 1000),
        )
        yield session


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        if settings.required_schema_revision:
            revisions = (
                (await connection.execute(text("SELECT version_num FROM alembic_version")))
                .scalars()
                .all()
            )
            if revisions != [settings.required_schema_revision]:
                raise SQLAlchemyError("database schema is not ready for this image")


async def dispose_engine() -> None:
    await engine.dispose()
