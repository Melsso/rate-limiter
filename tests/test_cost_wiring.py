import pytest
from fastapi import Depends, FastAPI

from rate_limiter import FixedWindow, RateLimit, rate_limit
from rate_limiter.middleware import RateLimitMiddleware


def same_client(request):
    return "u"


@pytest.mark.asyncio
async def test_decorator_static_cost(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=10, window=60)

    @app.get("/")
    @rate_limit(limiter, key_func=same_client, cost=4)
    async def root():
        return {}

    async with client_for(app) as c:
        first = await c.get("/")
        second = await c.get("/")
        third = await c.get("/")

    assert first.headers["X-RateLimit-Remaining"] == "6"
    assert second.headers["X-RateLimit-Remaining"] == "2"
    assert third.status_code == 429
    assert third.headers["X-RateLimit-Remaining"] == "2"


@pytest.mark.asyncio
async def test_dependency_callable_cost(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=10, window=60)

    def cost_from_query(request):
        return int(request.query_params.get("n", "1"))

    dependency = RateLimit(limiter, key_func=same_client, cost=cost_from_query)

    @app.get("/", dependencies=[Depends(dependency)])
    async def root():
        return {}

    async with client_for(app) as c:
        first = await c.get("/?n=7")
        too_big = await c.get("/?n=5")
        fits = await c.get("/?n=3")

    assert first.headers["X-RateLimit-Remaining"] == "3"
    assert too_big.status_code == 429
    assert fits.status_code == 200
    assert fits.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_middleware_callable_limit_per_tier(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=100, window=60)

    def by_api_key(request):
        return request.headers.get("x-api-key", "anon")

    def tier_limit(request):
        return 3 if request.headers.get("x-tier") == "pro" else 1

    app.add_middleware(
        RateLimitMiddleware, limiter=limiter, key_func=by_api_key, limit=tier_limit
    )

    @app.get("/")
    async def root():
        return {}

    free = {"x-api-key": "free-user"}
    pro = {"x-api-key": "pro-user", "x-tier": "pro"}

    async with client_for(app) as c:
        assert (await c.get("/", headers=free)).status_code == 200
        assert (await c.get("/", headers=free)).status_code == 429
        for _ in range(3):
            assert (await c.get("/", headers=pro)).status_code == 200
        blocked = await c.get("/", headers=pro)

    assert blocked.status_code == 429
    assert blocked.headers["X-RateLimit-Limit"] == "3"


@pytest.mark.parametrize("cost", [0, -1, 1.5])
def test_invalid_static_cost_raises_at_construction(broken_limiter, cost):
    with pytest.raises(ValueError):
        RateLimit(broken_limiter, cost=cost)
    with pytest.raises(ValueError):
        rate_limit(broken_limiter, cost=cost)
    with pytest.raises(ValueError):
        RateLimitMiddleware(None, limiter=broken_limiter, cost=cost)


@pytest.mark.parametrize("limit", [0, -1, 2.5])
def test_invalid_static_limit_raises_at_construction(broken_limiter, limit):
    with pytest.raises(ValueError):
        RateLimit(broken_limiter, limit=limit)
    with pytest.raises(ValueError):
        rate_limit(broken_limiter, limit=limit)
    with pytest.raises(ValueError):
        RateLimitMiddleware(None, limiter=broken_limiter, limit=limit)
