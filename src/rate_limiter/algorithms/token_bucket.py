import time
from pathlib import Path

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.schemas import RateLimitResult

BASE_DIR = Path(__file__).resolve().parent.parent
LUA_DIR = BASE_DIR / "lua"


class TokenBucket(RateLimiter):
    def __init__(
        self,
        redis: Redis,
        capacity: int,
        refill_rate: float,
    ):
        self.redis = redis
        self.capacity = capacity
        self.refill_rate = refill_rate

        script = (LUA_DIR / "token_bucket.lua").read_text()
        self.script = self.redis.register_script(script)

    async def allow(self, key: str) -> RateLimitResult:
        tokens_key = f"bucket:{key}:tokens"
        timestamp_key = f"bucket:{key}:timestamp"

        allowed, remaining, reset_after = await self.script(
            keys=[
                tokens_key,
                timestamp_key,
            ],
            args=[
                self.capacity,
                self.refill_rate,
                time.time(),
            ],
        )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            limit=self.capacity,
            remaining=int(remaining),
            reset_after=int(reset_after),
        )
