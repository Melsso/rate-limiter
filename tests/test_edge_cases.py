import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from rate_limiter import FixedWindow, SlidingWindow, forwarded_key_func
from rate_limiter.middleware import RateLimitMiddleware


@pytest.mark.asyncio
async def test_middleware_skips_options_by_default(redis):
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        limiter=FixedWindow(redis=redis, limit=1, window=60),
    )

    @app.get("/")
    async def root():
        return {}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(5):
            assert (await c.options("/")).status_code != 429


@pytest.mark.asyncio
async def test_fixed_window_retry_after_is_accurate(redis):
    limiter = FixedWindow(redis=redis, limit=1, window=1)
    await limiter.allow("u")
    blocked = await limiter.allow("u")
    assert not blocked.allowed
    assert 0 <= blocked.reset_after <= 1
    await asyncio.sleep(blocked.reset_after + 0.1)
    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_sliding_window_retry_after_is_accurate(redis):
    limiter = SlidingWindow(redis=redis, limit=1, window=1)
    await limiter.allow("u")
    blocked = await limiter.allow("u")
    assert not blocked.allowed
    assert 1 <= blocked.reset_after <= 2
    await asyncio.sleep(blocked.reset_after + 0.1)
    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_sliding_window_blocked_with_previous_window_weight(redis):
    limiter = SlidingWindow(redis=redis, limit=5, window=60)
    now = (await redis.time())[0]
    idx = now // 60
    await redis.hset("rl:sw:u", mapping={"w": idx, "c": 2, "p": 1000})
    result = await limiter.allow("u")
    assert not result.allowed
    assert 1 <= result.reset_after <= 120


def make_request(headers, client=("9.9.9.9", 1)):
    scope = {
        "type": "http",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        "client": client,
    }
    return Request(scope)


def test_forwarded_key_func():
    one = forwarded_key_func(1)
    two = forwarded_key_func(2)
    assert one(make_request({"x-forwarded-for": "evil, 1.2.3.4"})) == "1.2.3.4"
    assert two(make_request({"x-forwarded-for": "1.1.1.1, 2.2.2.2"})) == "1.1.1.1"
    assert two(make_request({"x-forwarded-for": "2.2.2.2"})) == "9.9.9.9"
    assert one(make_request({})) == "9.9.9.9"
