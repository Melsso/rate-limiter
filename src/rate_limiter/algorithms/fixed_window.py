from pathlib import Path

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.schemas import RateLimitResult

LUA_DIR = Path(__file__).resolve().parent.parent / "lua"


class FixedWindow(RateLimiter):
    def __init__(
        self,
        redis: Redis,
        limit: int,
        window: int,
        prefix: str = "rl:fw",
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window < 1:
            raise ValueError("window must be >= 1")

        self.redis = redis
        self.limit = limit
        self.window = window
        self.prefix = prefix
        self.script = redis.register_script((LUA_DIR / "fixed_window.lua").read_text())

    async def allow(self, key: str) -> RateLimitResult:
        current, ttl = await self.script(
            keys=[f"{self.prefix}:{key}"],
            args=[self.window],
        )
        current, ttl = int(current), int(ttl)

        return RateLimitResult(
            allowed=current <= self.limit,
            limit=self.limit,
            remaining=max(0, self.limit - current),
            reset_after=max(0, ttl),
        )
