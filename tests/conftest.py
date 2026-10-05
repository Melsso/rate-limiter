import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from testcontainers.redis import RedisContainer

from rate_limiter.algorithms.base import RateLimiter


class BrokenLimiter(RateLimiter):
    async def allow(self, key, cost=1, limit=None):
        raise RedisConnectionError("down")

    async def peek(self, key, cost=1, limit=None):
        raise RedisConnectionError("down")

    async def reset(self, key):
        raise RedisConnectionError("down")


@pytest.fixture(scope="session")
def redis_container():
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


@pytest.fixture
def broken_limiter():
    return BrokenLimiter()


@pytest.fixture
def client_for():
    def factory(app):
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    return factory
