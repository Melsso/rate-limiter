from fastapi import FastAPI

from rate_limiter.algorithms.fixed_window import FixedWindow
from rate_limiter.core.redis import redis
from rate_limiter.middleware.rate_limiter import RateLimitMiddleware


app = FastAPI()


limiter = FixedWindow(
    redis=redis,
    limit=5,
    window=60,
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