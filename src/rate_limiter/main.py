from fastapi import FastAPI

from rate_limiter.algorithms.token_bucket import TokenBucket
from rate_limiter.core.redis import redis
from rate_limiter.middleware.rate_limiter import RateLimitMiddleware


app = FastAPI()


# limiter = SlidingWindow(
#     redis=redis,
#     limit=5,
#     window=60,
# )
limiter = TokenBucket(
    redis=redis,
    capacity=5,
    refill_rate=5 / 60,
)

app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
)


@app.get("/")
async def root():
    return {
        "message": "Hello World"
    }