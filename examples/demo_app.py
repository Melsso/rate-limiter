import os

from fastapi import FastAPI
from redis.asyncio import Redis

from rate_limiter import FixedWindow
from rate_limiter.middleware import RateLimitMiddleware

redis = Redis.from_url(
    os.environ.get("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True,
)
limiter = FixedWindow(redis=redis, limit=5, window=60)

app = FastAPI()
app.add_middleware(RateLimitMiddleware, limiter=limiter)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World"}
