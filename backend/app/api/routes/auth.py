from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.dependencies import AuthGuardDep, SessionDep, SettingsDep
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    login_user,
    logout,
    register_user,
    rotate_refresh_token,
)

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    auth_guard: AuthGuardDep,
) -> AuthResponse:
    if not settings.public_registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="public registration is disabled",
        )
    await auth_guard.enforce_rate("register", payload.email, request)
    try:
        user, tokens = await register_user(session, payload.email, payload.password, settings)
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(status_code=409, detail="email already registered") from error
    return AuthResponse(user=user, **tokens.__dict__)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    auth_guard: AuthGuardDep,
) -> AuthResponse:
    await auth_guard.enforce_rate("login", payload.email, request)
    try:
        user, tokens = await login_user(session, payload.email, payload.password, settings)
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    await auth_guard.clear_login_rate(payload.email)
    return AuthResponse(user=user, **tokens.__dict__)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        tokens = await rotate_refresh_token(session, request.refresh_token, settings)
    except InvalidRefreshTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
        ) from error
    return TokenResponse(**tokens.__dict__)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def log_out(request: RefreshRequest, session: SessionDep) -> Response:
    await logout(session, request.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
