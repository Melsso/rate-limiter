from typing import Annotated

import pytest
from fastapi import FastAPI, HTTPException, Request, Response

from rate_limiter import FixedWindow, rate_limit


@pytest.mark.asyncio
async def test_headers_survive_handler_http_exception(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=3, window=60)

    @app.get("/async")
    @rate_limit(limiter, namespace="async")
    async def missing_async():
        raise HTTPException(404, "nope", headers={"X-Custom": "1"})

    @app.get("/sync")
    @rate_limit(limiter, namespace="sync")
    def missing_sync():
        raise HTTPException(404, "nope")

    async with client_for(app) as c:
        a = await c.get("/async")
        s = await c.get("/sync")

    assert a.status_code == 404
    assert a.headers["X-RateLimit-Limit"] == "3"
    assert a.headers["X-RateLimit-Remaining"] == "2"
    assert a.headers["X-Custom"] == "1"
    assert s.status_code == 404
    assert s.headers["X-RateLimit-Remaining"] == "2"


@pytest.mark.asyncio
async def test_stacked_rejection_headers_are_the_inner_limiters(redis, client_for):
    app = FastAPI()
    loose = FixedWindow(redis=redis, limit=5, window=60, prefix="rl:loose")
    strict = FixedWindow(redis=redis, limit=1, window=60, prefix="rl:strict")

    @app.get("/")
    @rate_limit(loose)
    @rate_limit(strict)
    async def root():
        return {}

    async with client_for(app) as c:
        await c.get("/")
        r = await c.get("/")

    assert r.status_code == 429
    assert r.headers["X-RateLimit-Limit"] == "1"
    assert int(r.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_annotated_request_and_response_are_reused(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=3, window=60)

    @app.get("/")
    @rate_limit(limiter)
    async def root(
        request: Annotated[Request, "marker"],
        response: Annotated[Response, "marker"],
    ):
        response.headers["X-Custom"] = "1"
        return {"path": request.url.path}

    async with client_for(app) as c:
        r = await c.get("/")

    assert r.status_code == 200
    assert r.json() == {"path": "/"}
    assert r.headers["X-Custom"] == "1"
    assert r.headers["X-RateLimit-Remaining"] == "2"


@pytest.mark.asyncio
async def test_reset_needs_the_namespaced_key(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    @app.get("/")
    @rate_limit(limiter, key_func=lambda request: "u", namespace="a")
    async def root():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 200
        assert (await c.get("/")).status_code == 429

        await limiter.reset("u")
        assert (await c.get("/")).status_code == 429

        await limiter.reset("a:u")
        assert (await c.get("/")).status_code == 200
