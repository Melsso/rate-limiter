import pytest

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from rate_limiter import FixedWindow, rate_limit


@pytest.mark.asyncio
async def test_rate_limit_decorator(redis):
    app = FastAPI()

    limiter = FixedWindow(
        redis=redis,
        limit=2,
        window=60,
    )

    @app.get("/")
    @rate_limit(limiter)
    async def root(request: Request):
        return {"message": "ok"}

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        first = await client.get("/")
        second = await client.get("/")
        third = await client.get("/")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429