from pathlib import Path

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.schemas.rate_limit import RateLimitResult


BASE_DIR = Path(__file__).resolve().parent.parent
LUA_DIR = BASE_DIR / "lua"


class FixedWindow(RateLimiter):
    def __init__(
        self,
        redis: Redis,
        limit: int,
        window: int,
    ):
        self.redis = redis
        self.limit = limit
        self.window = window

        script = (LUA_DIR / "fixed_window.lua").read_text()
        self.script = self.redis.register_script(script)

    async def allow(self, key: str) -> RateLimitResult:
        current, ttl = await self.script(
            keys=[key],
            args=[self.window],
        )

        current = int(current)
        ttl = int(ttl)

        return RateLimitResult(
            allowed=current <= self.limit,
            limit=self.limit,
            remaining=max(0, self.limit - current),
            reset_after=max(0, ttl),
        )