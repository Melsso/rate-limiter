import pytest
from fastapi import Depends, FastAPI
from redis.exceptions import RedisClusterException

from rate_limiter import MemoryFixedWindow, RateLimit
from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.middleware import RateLimitMiddleware


class ClusterDownLimiter(RateLimiter):
    async def allow(self, key, cost=1, limit=None):
        raise RedisClusterException("Redis Cluster cannot be connected")

    async def peek(self, key, cost=1, limit=None):
        raise RedisClusterException("Redis Cluster cannot be connected")

    async def reset(self, key):
        raise RedisClusterException("Redis Cluster cannot be connected")


def app_with(dependency):
    app = FastAPI()

    @app.get("/", dependencies=[Depends(dependency)])
    async def root():
        return {}

    return app


@pytest.mark.asyncio
async def test_cluster_exception_fails_open(client_for):
    app = app_with(RateLimit(ClusterDownLimiter()))

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 200


@pytest.mark.asyncio
async def test_cluster_exception_fails_closed(client_for):
    app = app_with(RateLimit(ClusterDownLimiter(), fail_open=False))

    async with client_for(app) as c:
        response = await c.get("/")

    assert response.status_code == 503
    assert response.json() == {"detail": "Rate limiter unavailable"}


@pytest.mark.asyncio
async def test_cluster_exception_uses_the_fallback(client_for):
    app = app_with(
        RateLimit(
            ClusterDownLimiter(),
            key_func=lambda request: "u",
            fallback=MemoryFixedWindow(limit=1, window=60),
        )
    )

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 200
        assert (await c.get("/")).status_code == 429


@pytest.mark.asyncio
async def test_middleware_handles_cluster_exception(client_for):
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware, limiter=ClusterDownLimiter(), fail_open=False
    )

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 503
