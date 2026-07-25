from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.redis import get_redis_client
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.models import User
from app.repositories.users import get_user_by_id
from app.services.auth_guard import AuthGuard
from app.services.demo_guard import DemoGuard

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_demo_guard(settings: SettingsDep) -> DemoGuard:
    return DemoGuard(settings, get_redis_client())


DemoGuardDep = Annotated[DemoGuard, Depends(get_demo_guard)]


async def get_auth_guard(settings: SettingsDep) -> AuthGuard:
    return AuthGuard(settings, get_redis_client())


AuthGuardDep = Annotated[AuthGuard, Depends(get_auth_guard)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except InvalidAccessTokenError as error:
        raise unauthorized from error

    user = await get_user_by_id(session, claims.user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
