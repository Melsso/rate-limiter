from typing import cast

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.commands.core import AsyncScript

RedisClient = Redis | RedisCluster


def register_script(client: RedisClient, script: str) -> AsyncScript:
    return cast(Redis, client).register_script(script)
