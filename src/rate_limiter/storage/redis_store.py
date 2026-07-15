from redis.asyncio import Redis

from rate_limiter.storage.base import Storage


class RedisStorage(Storage):

    def __init__(self, redis: Redis):
        self.redis = redis

    async def increment(self, key: str) -> int:
        return await self.redis.incr(key)

    async def get(self, key: str):
        return await self.redis.get(key)

    async def expire(self, key: str, seconds: int):
        await self.redis.expire(key, seconds)

    async def delete(self, key: str):
        await self.redis.delete(key)