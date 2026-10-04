import pytest
from fastapi import APIRouter, Depends, FastAPI

from rate_limiter import FixedWindow, RateLimit


@pytest.mark.asyncio
async def test_headers_on_dict_response(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=2, window=60)

    @app.get("/", dependencies=[Depends(RateLimit(limiter))])
    async def root():
        return {"ok": True}

    async with client_for(app) as c:
        r = await c.get("/")

    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == "2"
    assert r.headers["X-RateLimit-Remaining"] == "1"


@pytest.mark.asyncio
async def test_blocks_with_retry_after_and_json_body(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    @app.get("/", dependencies=[Depends(RateLimit(limiter))])
    async def root():
        return {"ok": True}

    async with client_for(app) as c:
        await c.get("/")
        r = await c.get("/")

    assert r.status_code == 429
    assert r.json() == {"detail": "Too Many Requests"}
    assert int(r.headers["Retry-After"]) >= 1
    assert r.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_sync_handler(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    @app.get("/", dependencies=[Depends(RateLimit(limiter))])
    def root():
        return {"ok": True}

    async with client_for(app) as c:
        assert (await c.get("/")).status_code == 200
        assert (await c.get("/")).status_code == 429


@pytest.mark.asyncio
async def test_router_level_dependency_covers_all_routes(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)
    router = APIRouter(dependencies=[Depends(RateLimit(limiter))])

    @router.get("/a")
    async def a():
        return {}

    @router.get("/b")
    async def b():
        return {}

    app.include_router(router)

    async with client_for(app) as c:
        assert (await c.get("/a")).status_code == 200
        assert (await c.get("/b")).status_code == 429


@pytest.mark.asyncio
async def test_key_func_namespace_and_exempt_when(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=1, window=60)

    def by_api_key(request):
        return request.headers.get("x-api-key", "anon")

    def is_admin(request):
        return request.headers.get("x-admin") == "1"

    rate_a = RateLimit(
        limiter, key_func=by_api_key, namespace="a", exempt_when=is_admin
    )
    rate_b = RateLimit(limiter, key_func=by_api_key, namespace="b")

    @app.get("/a", dependencies=[Depends(rate_a)])
    async def a():
        return {}

    @app.get("/b", dependencies=[Depends(rate_b)])
    async def b():
        return {}

    async with client_for(app) as c:
        key = {"x-api-key": "k"}
        assert (await c.get("/a", headers=key)).status_code == 200
        assert (await c.get("/a", headers=key)).status_code == 429
        assert (await c.get("/b", headers=key)).status_code == 200
        assert (await c.get("/a", headers={"x-api-key": "other"})).status_code == 200
        for _ in range(3):
            admin = {**key, "x-admin": "1"}
            assert (await c.get("/a", headers=admin)).status_code == 200


@pytest.mark.asyncio
async def test_fail_open_and_closed(broken_limiter, client_for):
    app = FastAPI()

    @app.get("/open", dependencies=[Depends(RateLimit(broken_limiter))])
    async def open_route():
        return {}

    @app.get(
        "/closed",
        dependencies=[Depends(RateLimit(broken_limiter, fail_open=False))],
    )
    async def closed_route():
        return {}

    async with client_for(app) as c:
        assert (await c.get("/open")).status_code == 200
        assert (await c.get("/closed")).status_code == 503
