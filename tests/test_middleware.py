import pytest
from fastapi import FastAPI

from rate_limiter import FixedWindow
from rate_limiter.middleware import RateLimitMiddleware


@pytest.mark.asyncio
async def test_rate_limit_middleware_blocks_requests(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=2, window=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    @app.get("/")
    async def root():
        return {"message": "ok"}

    async with client_for(app) as client:
        response_1 = await client.get("/")
        response_2 = await client.get("/")
        response_3 = await client.get("/")

    assert response_1.status_code == 200
    assert response_2.status_code == 200
    assert response_3.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_headers_are_present(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=5, window=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    @app.get("/")
    async def root():
        return {"message": "ok"}

    async with client_for(app) as client:
        response = await client.get("/")

    assert response.headers["X-RateLimit-Limit"] == "5"
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


@pytest.mark.asyncio
async def test_middleware_429_body_and_retry_after(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        await c.get("/")
        r = await c.get("/")

    assert r.status_code == 429
    assert r.json() == {"detail": "Too Many Requests"}
    assert int(r.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_middleware_async_key_func_isolates_clients(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    async def by_api_key(request):
        return request.headers.get("x-api-key", "anon")

    app.add_middleware(RateLimitMiddleware, limiter=limiter, key_func=by_api_key)

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/", headers={"x-api-key": "a"})).status_code == 200
        assert (await c.get("/", headers={"x-api-key": "b"})).status_code == 200
        assert (await c.get("/", headers={"x-api-key": "a"})).status_code == 429


@pytest.mark.asyncio
async def test_middleware_exclude_paths_and_exempt_when(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        exclude_paths=["/health"],
        exempt_when=lambda request: request.headers.get("x-admin") == "1",
    )

    @app.get("/health")
    async def health():
        return {}

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        for _ in range(3):
            assert (await c.get("/health")).status_code == 200
            assert (await c.get("/", headers={"x-admin": "1"})).status_code == 200


@pytest.mark.asyncio
async def test_middleware_fail_open(broken_limiter, client_for):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=broken_limiter)

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 200


@pytest.mark.asyncio
async def test_middleware_fail_closed(broken_limiter, client_for):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=broken_limiter, fail_open=False)

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 503
