from pathlib import Path

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.schemas import RateLimitResult

LUA_DIR = Path(__file__).resolve().parent.parent / "lua"


class TokenBucket(RateLimiter):
    def __init__(
        self,
        redis: Redis,
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
        self.script = redis.register_script((LUA_DIR / "token_bucket.lua").read_text())

    async def allow(self, key: str) -> RateLimitResult:
        allowed, remaining, reset_after = await self.script(
            keys=[f"{self.prefix}:{key}"],
            args=[self.capacity, self.refill_rate],
        )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            limit=self.capacity,
            remaining=int(remaining),
            reset_after=int(reset_after),
        )
