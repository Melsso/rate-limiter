from pathlib import Path

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.schemas import RateLimitResult

LUA_DIR = Path(__file__).resolve().parent.parent / "lua"


class SlidingWindow(RateLimiter):
    def __init__(
        self,
        redis: Redis,
        limit: int,
        window: int,
        prefix: str = "rl:sw",
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window < 1:
            raise ValueError("window must be >= 1")

        self.redis = redis
        self.limit = limit
        self.window = window
        self.prefix = prefix
        self.script = redis.register_script(
            (LUA_DIR / "sliding_window.lua").read_text()
        )

    async def allow(self, key: str) -> RateLimitResult:
        allowed, remaining, reset_after = await self.script(
            keys=[f"{self.prefix}:{key}"],
            args=[self.limit, self.window],
        )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            limit=self.limit,
            remaining=int(remaining),
            reset_after=int(reset_after),
        )
