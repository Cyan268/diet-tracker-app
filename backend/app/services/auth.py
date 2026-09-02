from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    digest_refresh_token,
    dummy_password_hash,
    hash_password,
    verify_password,
)
from app.models import RefreshToken, User
from app.repositories.refresh_tokens import get_refresh_token_for_update, revoke_active_family
from app.repositories.users import get_user_by_email, get_user_by_id


class EmailAlreadyRegisteredError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class InvalidRefreshTokenError(ValueError):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _build_refresh_token(
    user_id: UUID,
    family_id: UUID,
    settings: Settings,
) -> tuple[str, RefreshToken]:
    raw_token = create_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=digest_refresh_token(raw_token),
        family_id=family_id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    return raw_token, row


def _build_token_pair(user_id: UUID, raw_refresh_token: str, settings: Settings) -> TokenPair:
    access_token, expires_in = create_access_token(user_id, settings)
    return TokenPair(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        expires_in=expires_in,
    )


async def register_user(
    session: AsyncSession,
    email: str,
    password: str,
    settings: Settings,
) -> tuple[User, TokenPair]:
    normalized_email = normalize_email(email)
    if await get_user_by_email(session, normalized_email) is not None:
        raise EmailAlreadyRegisteredError

    user = User(email=normalized_email, password_hash=await hash_password(password))
    session.add(user)
    try:
        await session.flush()
        raw_refresh_token, refresh_row = _build_refresh_token(user.id, uuid4(), settings)
        session.add(refresh_row)
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise EmailAlreadyRegisteredError from error

    await session.refresh(user)
    return user, _build_token_pair(user.id, raw_refresh_token, settings)


async def login_user(
    session: AsyncSession,
    email: str,
    password: str,
    settings: Settings,
) -> tuple[User, TokenPair]:
    user = await get_user_by_email(session, normalize_email(email))
    candidate_hash = user.password_hash if user is not None else dummy_password_hash
    password_is_valid = await verify_password(password, candidate_hash)
    if user is None or not user.is_active or not password_is_valid:
        raise InvalidCredentialsError

    raw_refresh_token, refresh_row = _build_refresh_token(user.id, uuid4(), settings)
    session.add(refresh_row)
    await session.commit()
    return user, _build_token_pair(user.id, raw_refresh_token, settings)


async def rotate_refresh_token(
    session: AsyncSession,
    raw_token: str,
    settings: Settings,
) -> TokenPair:
    current = await get_refresh_token_for_update(session, digest_refresh_token(raw_token))
    if current is None:
        raise InvalidRefreshTokenError

    now = datetime.now(UTC)
    if current.revoked_at is not None:
        await revoke_active_family(session, current.family_id, now)
        await session.commit()
        raise InvalidRefreshTokenError
    if _is_expired(current.expires_at, now):
        current.revoked_at = now
        await session.commit()
        raise InvalidRefreshTokenError

    user = await get_user_by_id(session, current.user_id)
    if user is None or not user.is_active:
        await revoke_active_family(session, current.family_id, now)
        await session.commit()
        raise InvalidRefreshTokenError

    new_raw_token, replacement = _build_refresh_token(user.id, current.family_id, settings)
    session.add(replacement)
    await session.flush()
    current.revoked_at = now
    current.replaced_by_id = replacement.id
    await session.commit()
    return _build_token_pair(user.id, new_raw_token, settings)


async def logout(session: AsyncSession, raw_token: str) -> None:
    current = await get_refresh_token_for_update(session, digest_refresh_token(raw_token))
    if current is not None and current.revoked_at is None:
        current.revoked_at = datetime.now(UTC)
        await session.commit()
