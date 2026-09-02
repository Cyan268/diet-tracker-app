import asyncio
import logging
import secrets
from datetime import date

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import session_factory
from app.core.redis import get_redis_client
from app.services.demo_data import resolve_demo_anchor_date, seed_demo_account

_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

logger = logging.getLogger("nutripilot.demo_reset")


async def reset_demo_once(
    settings: Settings,
    *,
    redis: Redis | None = None,
    sessions: async_sessionmaker[AsyncSession] = session_factory,
    anchor_date: date | None = None,
) -> bool:
    password = settings.demo_reset_password
    if password is None:
        raise RuntimeError("demo reset password is not configured")
    redis_client = redis or get_redis_client()
    lock_key = "nutripilot:demo-reset:lock"
    lock_token = secrets.token_hex(16)
    acquired = await redis_client.set(
        lock_key,
        lock_token,
        nx=True,
        ex=settings.demo_reset_lock_ttl_seconds,
    )
    if not acquired:
        return False
    try:
        async with sessions() as session:
            await seed_demo_account(
                session,
                email=settings.demo_reset_email,
                password=password.get_secret_value(),
                anchor_date=anchor_date or resolve_demo_anchor_date(settings),
                reset_existing=True,
            )
        logger.info("demo.reset.completed", extra={"event": "demo.reset.completed"})
        return True
    finally:
        try:
            await redis_client.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)
        except RedisError as error:
            logger.warning(
                "demo.reset.lock_release_failed",
                extra={
                    "event": "demo.reset.lock_release_failed",
                    "error_type": type(error).__name__,
                },
            )


async def run_demo_reset_loop(settings: Settings) -> None:
    interval_seconds = settings.demo_reset_interval_minutes * 60
    if interval_seconds <= 0:
        return
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await reset_demo_once(settings)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error(
                "demo.reset.failed",
                extra={"event": "demo.reset.failed", "error_type": type(error).__name__},
            )
