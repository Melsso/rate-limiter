from redis.asyncio import Redis

from rate_limiter.core.config import settings


redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)