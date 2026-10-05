from pathlib import Path

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter, check_cost, check_limit
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

    async def _evaluate(
        self, key: str, cost: int, limit: int | None, consume: bool
    ) -> RateLimitResult:
        check_cost(cost)
        if limit is not None:
            check_limit(limit)
        effective = self.limit if limit is None else limit

        allowed, remaining, reset_after = await self.script(
            keys=[f"{self.prefix}:{key}"],
            args=[effective, self.window, cost, int(consume)],
        )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            limit=effective,
            remaining=int(remaining),
            reset_after=int(reset_after),
        )

    async def allow(
        self, key: str, cost: int = 1, limit: int | None = None
    ) -> RateLimitResult:
        return await self._evaluate(key, cost, limit, consume=True)

    async def peek(
        self, key: str, cost: int = 1, limit: int | None = None
    ) -> RateLimitResult:
        return await self._evaluate(key, cost, limit, consume=False)

    async def reset(self, key: str) -> None:
        await self.redis.delete(f"{self.prefix}:{key}")
