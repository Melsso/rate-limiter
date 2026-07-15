import time

from redis.asyncio import Redis

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.schemas import RateLimitResult


class SlidingWindow(RateLimiter):
    def __init__(
        self,
        redis: Redis,
        limit: int,
        window: int,
    ):
        self.redis = redis
        self.limit = limit
        self.window = window

    async def allow(self, key: str) -> RateLimitResult:
        now = int(time.time())
        current_window = now // self.window
        previous_window = current_window - 1

        current_key = f"rate:{key}:{current_window}"
        previous_key = f"rate:{key}:{previous_window}"

        current_count = await self.redis.get(current_key)
        previous_count = await self.redis.get(previous_key)

        current_count = int(current_count or 0)
        previous_count = int(previous_count or 0)

        elapsed = now % self.window
        weight = (self.window - elapsed) / self.window

        estimated_count = int(
            previous_count * weight + current_count
        )

        allowed = estimated_count < self.limit

        if allowed:
            pipe = self.redis.pipeline()

            pipe.incr(current_key)
            pipe.expire(current_key, self.window * 2)

            await pipe.execute()

            current_count += 1
            estimated_count = int(
                previous_count * weight + current_count
            )

        reset_after = self.window - elapsed

        return RateLimitResult(
            allowed=allowed,
            limit=self.limit,
            remaining=max(
                0,
                self.limit - estimated_count,
            ),
            reset_after=reset_after,
        )