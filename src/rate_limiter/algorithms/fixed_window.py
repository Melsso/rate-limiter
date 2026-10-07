from pathlib import Path
from typing import Self

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter, check_cost, check_limit
from rate_limiter.limits import parse_limit
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

    @classmethod
    def from_limit(cls, redis: Redis, spec: str, prefix: str = "rl:fw") -> Self:
        limit, window = parse_limit(spec)
        return cls(redis, limit, window, prefix=prefix)

    async def _evaluate(
        self, key: str, cost: int, limit: int | None, consume: bool
    ) -> RateLimitResult:
        check_cost(cost)
        if limit is not None:
            check_limit(limit)
        effective = self.limit if limit is None else limit

        allowed, current, ttl = await self.script(
            keys=[f"{self.prefix}:{key}"],
            args=[effective, self.window, cost, int(consume)],
        )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            limit=effective,
            remaining=max(0, effective - int(current)),
            reset_after=max(0, int(ttl)),
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
