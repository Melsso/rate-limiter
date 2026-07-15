import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from rate_limiter import FixedWindow
from rate_limiter.middleware import RateLimitMiddleware


@pytest.mark.asyncio
async def test_rate_limit_middleware_blocks_requests(redis):
    app = FastAPI()

    limiter = FixedWindow(
        redis=redis,
        limit=2,
        window=60,
    )

    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
    )

    @app.get("/")
    async def root():
        return {"message": "ok"}

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response_1 = await client.get("/")
        response_2 = await client.get("/")
        response_3 = await client.get("/")

    assert response_1.status_code == 200
    assert response_2.status_code == 200
    assert response_3.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_headers_are_present(redis):
    app = FastAPI()

    limiter = FixedWindow(
        redis=redis,
        limit=5,
        window=60,
    )

    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
    )

    @app.get("/")
    async def root():
        return {"message": "ok"}

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/")

    assert response.headers["X-RateLimit-Limit"] == "5"
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers
