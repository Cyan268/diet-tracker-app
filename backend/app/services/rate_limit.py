import math
from dataclasses import dataclass

from redis.asyncio import Redis

_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        current, ttl_ms = await self.redis.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            key,
            window_seconds * 1000,
        )
        retry_after = max(1, math.ceil(max(0, int(ttl_ms)) / 1000))
        return RateLimitResult(
            allowed=int(current) <= limit,
            retry_after_seconds=retry_after,
        )

    async def clear(self, key: str) -> None:
        await self.redis.delete(key)
