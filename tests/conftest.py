import pytest_asyncio
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer


@pytest_asyncio.fixture(scope="session")
async def redis_container():
    with RedisContainer("redis:8-alpine") as container:
        yield container


@pytest_asyncio.fixture
async def redis(redis_container):
    client = Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        decode_responses=True,
    )

    yield client

    await client.flushall()
    await client.aclose()
