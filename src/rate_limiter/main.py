from fastapi import FastAPI

from rate_limiter.core.container import limiter
from rate_limiter.core.redis import redis
from rate_limiter.middleware.rate_limiter import RateLimitMiddleware


app = FastAPI()
app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
)


@app.get("/")
async def root():
    return {
        "message": "Hello World"
    }