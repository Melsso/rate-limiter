import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from rate_limiter import FixedWindow, rate_limit


@pytest.mark.asyncio
async def test_no_request_param_needed_and_headers_on_dict(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=2, window=60)

    @app.get("/")
    @rate_limit(limiter)
    async def root():
        return {"ok": True}

    async with client_for(app) as c:
        r = await c.get("/")

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert r.headers["X-RateLimit-Limit"] == "2"
    assert r.headers["X-RateLimit-Remaining"] == "1"


@pytest.mark.asyncio
async def test_blocks_with_json_body_and_retry_after(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    @app.get("/")
    @rate_limit(limiter)
    async def root():
        return {"ok": True}

    async with client_for(app) as c:
        await c.get("/")
        r = await c.get("/")

    assert r.status_code == 429
    assert r.json() == {"detail": "Too Many Requests"}
    assert int(r.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_sync_handler_with_params_keeps_validation(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=5, window=60)

    @app.get("/items/{item_id}")
    @rate_limit(limiter)
    def item(item_id: int, q: str = "x"):
        return {"id": item_id, "q": q}

    async with client_for(app) as c:
        ok = await c.get("/items/5?q=y")
        bad = await c.get("/items/abc")

    assert ok.json() == {"id": 5, "q": "y"}
    assert ok.headers["X-RateLimit-Remaining"] == "4"
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_headers_on_response_object_return(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=3, window=60)

    @app.get("/")
    @rate_limit(limiter)
    async def root():
        return JSONResponse({"ok": True})

    async with client_for(app) as c:
        r = await c.get("/")

    assert r.headers["X-RateLimit-Remaining"] == "2"


@pytest.mark.asyncio
async def test_handler_declaring_request_and_response(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=3, window=60)

    @app.get("/")
    @rate_limit(limiter)
    async def root(request: Request, response: Response):
        response.headers["X-Custom"] = "1"
        return {"path": request.url.path}

    async with client_for(app) as c:
        r = await c.get("/")

    assert r.json() == {"path": "/"}
    assert r.headers["X-Custom"] == "1"
    assert r.headers["X-RateLimit-Remaining"] == "2"


@pytest.mark.asyncio
async def test_stacked_decorators(redis, client_for):
    app = FastAPI()
    loose = FixedWindow(redis=redis, limit=5, window=60, prefix="rl:loose")
    strict = FixedWindow(redis=redis, limit=1, window=60, prefix="rl:strict")

    @app.get("/")
    @rate_limit(loose)
    @rate_limit(strict)
    async def root():
        return {"ok": True}

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 200
        assert (await c.get("/")).status_code == 429


@pytest.mark.asyncio
async def test_namespace_separates_routes_sharing_a_limiter(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    @app.get("/a")
    @rate_limit(limiter, namespace="a")
    async def a():
        return {}

    @app.get("/b")
    @rate_limit(limiter, namespace="b")
    async def b():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/a")).status_code == 200
        assert (await c.get("/b")).status_code == 200
        assert (await c.get("/a")).status_code == 429


@pytest.mark.asyncio
async def test_async_key_func_and_exempt_when(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    async def by_api_key(request):
        return request.headers.get("x-api-key", "anon")

    def is_admin(request):
        return request.headers.get("x-admin") == "1"

    @app.get("/")
    @rate_limit(limiter, key_func=by_api_key, exempt_when=is_admin)
    async def root():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/", headers={"x-api-key": "a"})).status_code == 200
        assert (await c.get("/", headers={"x-api-key": "b"})).status_code == 200
        assert (await c.get("/", headers={"x-api-key": "a"})).status_code == 429
        for _ in range(3):
            r = await c.get("/", headers={"x-api-key": "a", "x-admin": "1"})
            assert r.status_code == 200


@pytest.mark.asyncio
async def test_fail_open_and_closed(broken_limiter, client_for):
    app = FastAPI()

    @app.get("/open")
    @rate_limit(broken_limiter)
    async def open_route():
        return {}

    @app.get("/closed")
    @rate_limit(broken_limiter, fail_open=False)
    async def closed_route():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/open")).status_code == 200
        assert (await c.get("/closed")).status_code == 503
