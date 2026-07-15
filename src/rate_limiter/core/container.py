from rate_limiter import FixedWindow, TokenBucket, SlidingWindow

from rate_limiter.core.redis import redis
from rate_limiter.core.config import settings


limiter = FixedWindow(
    redis=redis,
    limit=settings.rate_limit,
    window=settings.rate_window,
)

# limiter = SlidingWindow(
#     redis=redis,
#     limit=5,
#     window=60,
# )

# limiter = TokenBucket(
#     redis=redis,
#     capacity=5,
#     refill_rate=5 / 60,
# )