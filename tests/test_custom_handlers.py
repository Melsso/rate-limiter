import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

from rate_limiter import (
    FixedWindow,
    RateLimit,
    RateLimiterUnavailableError,
    RateLimitExceeded,
    RateLimitResult,
    rate_limit,
)
from rate_limiter.middleware import RateLimitMiddleware


def same_client(request):
    return "u"


def test_rate_limit_exceeded_carries_the_result():
    result = RateLimitResult(allowed=False, limit=5, remaining=0, reset_after=0)

    exc = RateLimitExceeded(result)

    assert exc.status_code == 429
    assert exc.detail == "Too Many Requests"
    assert exc.result is result
    assert exc.headers["Retry-After"] == "1"
    assert exc.headers["X-RateLimit-Limit"] == "5"


def test_unavailable_error_defaults():
    exc = RateLimiterUnavailableError()

    assert exc.status_code == 503
    assert exc.detail == "Rate limiter unavailable"


@pytest.mark.asyncio
async def test_custom_429_handler_for_dependency_and_decorator(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    @app.exception_handler(RateLimitExceeded)
    async def too_many(request, exc):
        return JSONResponse(
            {"error": "slow down", "limit": exc.result.limit},
            status_code=429,
            headers=exc.headers,
        )

    @app.get("/dep", dependencies=[Depends(RateLimit(limiter, key_func=same_client))])
    async def dep():
        return {}

    @app.get("/dec")
    @rate_limit(limiter, key_func=same_client, namespace="dec")
    async def dec():
        return {}

    async with client_for(app) as c:
        await c.get("/dep")
        await c.get("/dec")
        blocked_dep = await c.get("/dep")
        blocked_dec = await c.get("/dec")

    for blocked in (blocked_dep, blocked_dec):
        assert blocked.status_code == 429
        assert blocked.json() == {"error": "slow down", "limit": 1}
        assert int(blocked.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_custom_503_handler(broken_limiter, client_for):
    app = FastAPI()

    @app.exception_handler(RateLimiterUnavailableError)
    async def unavailable(request, exc):
        return JSONResponse({"error": "try later"}, status_code=503)

    @app.get(
        "/",
        dependencies=[Depends(RateLimit(broken_limiter, fail_open=False))],
    )
    async def root():
        return {}

    async with client_for(app) as c:
        response = await c.get("/")

    assert response.status_code == 503
    assert response.json() == {"error": "try later"}


@pytest.mark.asyncio
async def test_middleware_on_limit_sync_callback(redis, client_for):
    app = FastAPI()

    def on_limit(request, result):
        return PlainTextResponse(f"retry in {result.reset_after}s", status_code=429)

    app.add_middleware(
        RateLimitMiddleware,
        limiter=FixedWindow(redis=redis, limit=1, window=60),
        key_func=same_client,
        on_limit=on_limit,
    )

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        await c.get("/")
        blocked = await c.get("/")

    assert blocked.status_code == 429
    assert blocked.text.startswith("retry in ")
    assert blocked.headers["X-RateLimit-Limit"] == "1"
    assert int(blocked.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_middleware_on_limit_async_callback_keeps_its_own_headers(
    redis, client_for
):
    app = FastAPI()

    async def on_limit(request, result):
        return JSONResponse(
            {"error": "slow down"}, status_code=429, headers={"Retry-After": "99"}
        )

    app.add_middleware(
        RateLimitMiddleware,
        limiter=FixedWindow(redis=redis, limit=1, window=60),
        key_func=same_client,
        on_limit=on_limit,
    )

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        await c.get("/")
        blocked = await c.get("/")

    assert blocked.json() == {"error": "slow down"}
    assert blocked.headers["Retry-After"] == "99"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_middleware_default_503_is_json(broken_limiter, client_for):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=broken_limiter, fail_open=False)

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        response = await c.get("/")

    assert response.status_code == 503
    assert response.json() == {"detail": "Rate limiter unavailable"}


@pytest.mark.asyncio
async def test_middleware_on_unavailable_callback(broken_limiter, client_for):
    app = FastAPI()

    async def on_unavailable(request):
        return JSONResponse({"error": "try later"}, status_code=503)

    app.add_middleware(
        RateLimitMiddleware,
        limiter=broken_limiter,
        fail_open=False,
        on_unavailable=on_unavailable,
    )

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        response = await c.get("/")

    assert response.status_code == 503
    assert response.json() == {"error": "try later"}
