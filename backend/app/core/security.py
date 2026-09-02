from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

import jwt
from anyio import to_thread
from pwdlib import PasswordHash

from app.core.config import Settings

password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash("timing-equalization-only")


class InvalidAccessTokenError(ValueError):
    """Raised when an access token cannot be trusted."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    token_id: UUID


async def hash_password(password: str) -> str:
    return await to_thread.run_sync(password_hash.hash, password)


async def verify_password(password: str, encoded_hash: str) -> bool:
    return await to_thread.run_sync(password_hash.verify, password, encoded_hash)


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    token_id = uuid4()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "jti": str(token_id),
            "type": "access",
            "iat": now,
            "exp": now + lifetime,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "jti", "type", "iat", "exp", "iss", "aud"]},
        )
        if payload["type"] != "access":
            raise InvalidAccessTokenError
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            token_id=UUID(payload["jti"]),
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise InvalidAccessTokenError from error


def create_refresh_token() -> str:
    return token_urlsafe(48)


def digest_refresh_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
