from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken


async def get_refresh_token_for_update(
    session: AsyncSession,
    token_hash: str,
) -> RefreshToken | None:
    statement = select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    return await session.scalar(statement)


async def revoke_active_family(
    session: AsyncSession,
    family_id: UUID,
    revoked_at: datetime,
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )
