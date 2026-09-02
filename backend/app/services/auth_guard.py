import hashlib
import hmac
import logging
from typing import Literal

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.client_address import resolve_client_address
from app.core.config import Settings
from app.services.auth import normalize_email
from app.services.rate_limit import RedisRateLimiter

AuthRateAction = Literal["login", "register"]

logger = logging.getLogger("nutripilot.auth_guard")


class AuthGuard:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self.settings = settings
        self.rate_limiter = RedisRateLimiter(redis)

    def _rate_key(self, action: AuthRateAction, email: str) -> str:
        normalized_email = normalize_email(email)
        message = f"auth-rate:v1:{action}:{normalized_email}".encode()
        secret = self.settings.rate_limit_hmac_secret.get_secret_value().encode()
        digest = hmac.new(secret, message, hashlib.sha256).hexdigest()
        return f"nutripilot:auth-rate:{action}:{digest}"

    def _visitor_rate_key(self, request: Request) -> str:
        address = resolve_client_address(request.scope, self.settings.trusted_proxy_cidrs)
        message = f"auth-visitor-rate:v1:{address}".encode()
        secret = self.settings.rate_limit_hmac_secret.get_secret_value().encode()
        digest = hmac.new(secret, message, hashlib.sha256).hexdigest()
        return f"nutripilot:auth-visitor:{digest}"

    async def enforce_rate(
        self,
        action: AuthRateAction,
        email: str,
        request: Request,
    ) -> None:
        if not self.settings.auth_protection_enabled:
            return
        await self._enforce_key(
            self._visitor_rate_key(request),
            limit=self.settings.auth_visitor_requests_per_window,
            detail="authentication visitor limit reached; retry later",
        )
        limit = (
            self.settings.auth_login_attempts_per_window
            if action == "login"
            else self.settings.auth_register_attempts_per_window
        )
        await self._enforce_key(
            self._rate_key(action, email),
            limit=limit,
            detail=f"{action} attempt limit reached; retry later",
        )

    async def _enforce_key(self, key: str, *, limit: int, detail: str) -> None:
        try:
            result = await self.rate_limiter.hit(
                key,
                limit=limit,
                window_seconds=self.settings.auth_rate_limit_window_seconds,
            )
        except RedisError as error:
            self._handle_redis_error(error)
            return
        if result.allowed:
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(result.retry_after_seconds)},
        )

    async def clear_login_rate(self, email: str) -> None:
        if not self.settings.auth_protection_enabled:
            return
        try:
            await self.rate_limiter.clear(self._rate_key("login", email))
        except RedisError as error:
            logger.warning(
                "auth.protection.login_counter_clear_failed",
                extra={
                    "event": "auth.protection.login_counter_clear_failed",
                    "error_type": type(error).__name__,
                },
            )

    def _handle_redis_error(self, error: RedisError) -> None:
        logger.warning(
            "auth.protection.redis_unavailable",
            extra={
                "event": "auth.protection.redis_unavailable",
                "error_type": type(error).__name__,
            },
        )
        if self.settings.auth_protection_fail_closed:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="authentication protection is temporarily unavailable",
                headers={"Retry-After": "30"},
            ) from error
