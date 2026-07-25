import logging
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AssistantConversation, AssistantMessage, FoodItem, FoodLog, User
from app.services.rate_limit import RedisRateLimiter

DemoRateAction = Literal["write", "ai"]
DemoQuotaResource = Literal["logs", "private_foods", "conversations", "messages"]

logger = logging.getLogger("nutripilot.demo_guard")


class DemoGuard:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self.settings = settings
        self.rate_limiter = RedisRateLimiter(redis)

    async def enforce_rate(self, user: User, action: DemoRateAction) -> None:
        if not user.is_demo or not self.settings.demo_protection_enabled:
            return
        limit = (
            self.settings.demo_write_requests_per_window
            if action == "write"
            else self.settings.demo_ai_requests_per_window
        )
        key = f"nutripilot:demo-rate:{user.id}:{action}"
        try:
            result = await self.rate_limiter.hit(
                key,
                limit=limit,
                window_seconds=self.settings.demo_rate_limit_window_seconds,
            )
        except RedisError as error:
            logger.warning(
                "demo.protection.redis_unavailable",
                extra={
                    "event": "demo.protection.redis_unavailable",
                    "error_type": type(error).__name__,
                },
            )
            if self.settings.demo_protection_fail_closed:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="demo protection is temporarily unavailable",
                    headers={"Retry-After": "30"},
                ) from error
            return
        if result.allowed:
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="demo account request limit reached; retry later",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )

    async def enforce_capacity(
        self,
        session: AsyncSession,
        user: User,
        resource: DemoQuotaResource,
        *,
        conversation_id: UUID | None = None,
    ) -> None:
        if not user.is_demo or not self.settings.demo_protection_enabled:
            return
        if resource == "logs":
            statement = select(func.count(FoodLog.id)).where(FoodLog.user_id == user.id)
            limit = self.settings.demo_max_logs
        elif resource == "private_foods":
            statement = select(func.count(FoodItem.id)).where(FoodItem.owner_user_id == user.id)
            limit = self.settings.demo_max_private_foods
        elif resource == "conversations":
            statement = select(func.count(AssistantConversation.id)).where(
                AssistantConversation.user_id == user.id
            )
            limit = self.settings.demo_max_conversations
        else:
            if conversation_id is None:
                raise ValueError("conversation_id is required for message quota")
            statement = select(func.count(AssistantMessage.id)).where(
                AssistantMessage.conversation_id == conversation_id
            )
            limit = self.settings.demo_max_messages_per_conversation
        count = int(await session.scalar(statement) or 0)
        required_slots = 2 if resource == "messages" else 1
        if count + required_slots <= limit:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"demo account {resource} quota reached; wait for reset",
        )
