from pathlib import Path
from typing import Self

from rate_limiter.algorithms.base import RateLimiter, check_cost, check_limit
from rate_limiter.clients import RedisClient, register_script
from rate_limiter.limits import parse_limit
from rate_limiter.schemas import RateLimitResult

LUA_DIR = Path(__file__).resolve().parent.parent / "lua"


class TokenBucket(RateLimiter):
    def __init__(
        self,
        redis: RedisClient,
        capacity: int,
        refill_rate: float,
        prefix: str = "rl:tb",
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be > 0")

        self.redis = redis
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.prefix = prefix
        self.script = register_script(redis, (LUA_DIR / "token_bucket.lua").read_text())

    @classmethod
    def from_limit(cls, redis: RedisClient, spec: str, prefix: str = "rl:tb") -> Self:
        capacity, seconds = parse_limit(spec)
        return cls(redis, capacity, capacity / seconds, prefix=prefix)

    async def _evaluate(
        self, key: str, cost: int, limit: int | None, consume: bool
    ) -> RateLimitResult:
        check_cost(cost)
        if limit is None:
            capacity = self.capacity
            rate = self.refill_rate
        else:
            check_limit(limit)
            capacity = limit
            rate = self.refill_rate * limit / self.capacity

        allowed, remaining, reset_after = await self.script(
            keys=[f"{self.prefix}:{key}"],
            args=[capacity, rate, cost, int(consume)],
        )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            limit=capacity,
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
