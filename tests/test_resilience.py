import logging

import pytest
from fastapi import Depends, FastAPI
from redis.exceptions import ConnectionError as RedisConnectionError

from rate_limiter import MemoryFixedWindow, RateLimit, RateLimitResult
from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core import health
from rate_limiter.middleware import RateLimitMiddleware


class FlakyLimiter(RateLimiter):
    def __init__(self, healthy=False):
        self.healthy = healthy
        self.calls = 0

    async def allow(self, key, cost=1, limit=None):
        self.calls += 1
        if not self.healthy:
            raise RedisConnectionError("down")
        return RateLimitResult(allowed=True, limit=10, remaining=9, reset_after=60)

    async def peek(self, key, cost=1, limit=None):
        return await self.allow(key, cost, limit)

    async def reset(self, key):
        return None


class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def fake_time(monkeypatch):
    fake = FakeTime()
    monkeypatch.setattr(health, "_now", fake)
    monkeypatch.setattr(health, "_last_warning", float("-inf"))
    return fake


def same_client(request):
    return "u"


def app_with(*routes):
    app = FastAPI()
    for path, dependency in routes:

        @app.get(path, dependencies=[Depends(dependency)])
        async def handler():
            return {}

    return app


@pytest.mark.asyncio
async def test_breaker_skips_the_backend_during_cooldown(fake_time, client_for):
    limiter = FlakyLimiter()
    app = app_with(("/", RateLimit(limiter, cooldown=5)))

    async with client_for(app) as c:
        for _ in range(3):
            assert (await c.get("/")).status_code == 200
        assert limiter.calls == 1

        fake_time.advance(6)
        assert (await c.get("/")).status_code == 200
        assert limiter.calls == 2

        assert (await c.get("/")).status_code == 200
        assert limiter.calls == 2


@pytest.mark.asyncio
async def test_breaker_closes_after_a_successful_probe(fake_time, client_for):
    limiter = FlakyLimiter()
    app = app_with(("/", RateLimit(limiter, cooldown=5)))

    async with client_for(app) as c:
        await c.get("/")
        assert limiter.calls == 1

        limiter.healthy = True
        fake_time.advance(6)
        for _ in range(3):
            assert (await c.get("/")).status_code == 200

    assert limiter.calls == 4


@pytest.mark.asyncio
async def test_cooldown_zero_disables_the_breaker(fake_time, client_for):
    limiter = FlakyLimiter()
    app = app_with(("/", RateLimit(limiter, cooldown=0)))

    async with client_for(app) as c:
        for _ in range(3):
            await c.get("/")

    assert limiter.calls == 3


@pytest.mark.asyncio
async def test_fail_closed_rejects_without_calling_an_open_breaker(
    fake_time, client_for
):
    limiter = FlakyLimiter()
    app = app_with(("/", RateLimit(limiter, fail_open=False, cooldown=5)))

    async with client_for(app) as c:
        first = await c.get("/")
        second = await c.get("/")

    assert first.status_code == 503
    assert second.status_code == 503
    assert second.json() == {"detail": "Rate limiter unavailable"}
    assert limiter.calls == 1


@pytest.mark.asyncio
async def test_guards_sharing_a_limiter_share_the_breaker(fake_time, client_for):
    limiter = FlakyLimiter()
    app = app_with(
        ("/a", RateLimit(limiter, namespace="a")),
        ("/b", RateLimit(limiter, namespace="b")),
    )

    async with client_for(app) as c:
        await c.get("/a")
        await c.get("/b")

    assert limiter.calls == 1


@pytest.mark.asyncio
async def test_fallback_enforces_limits_while_the_backend_is_down(
    fake_time, client_for
):
    fallback = MemoryFixedWindow(limit=1, window=60)
    app = app_with(
        ("/", RateLimit(FlakyLimiter(), key_func=same_client, fallback=fallback))
    )

    async with client_for(app) as c:
        first = await c.get("/")
        second = await c.get("/")

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "1"
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_fallback_takes_precedence_over_fail_open(fake_time, client_for):
    fallback = MemoryFixedWindow(limit=5, window=60)
    app = app_with(
        (
            "/",
            RateLimit(
                FlakyLimiter(),
                key_func=same_client,
                fail_open=False,
                fallback=fallback,
            ),
        )
    )

    async with client_for(app) as c:
        response = await c.get("/")

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "4"


@pytest.mark.asyncio
async def test_middleware_uses_the_fallback(fake_time, client_for):
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        limiter=FlakyLimiter(),
        key_func=same_client,
        fallback=MemoryFixedWindow(limit=1, window=60),
    )

    @app.get("/")
    async def root():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 200
        assert (await c.get("/")).status_code == 429


@pytest.mark.asyncio
async def test_warning_is_throttled_across_guards(fake_time, client_for, caplog):
    limiter = FlakyLimiter()
    app = app_with(
        ("/a", RateLimit(limiter, namespace="a", cooldown=0)),
        ("/b", RateLimit(limiter, namespace="b", cooldown=0)),
    )

    def warnings():
        return [r for r in caplog.records if r.name == "rate_limiter"]

    with caplog.at_level(logging.WARNING, logger="rate_limiter"):
        async with client_for(app) as c:
            await c.get("/a")
            await c.get("/b")
            await c.get("/a")
            assert len(warnings()) == 1

            fake_time.advance(31)
            await c.get("/b")
            assert len(warnings()) == 2


def test_negative_cooldown_raises():
    with pytest.raises(ValueError):
        RateLimit(FlakyLimiter(), cooldown=-1)
