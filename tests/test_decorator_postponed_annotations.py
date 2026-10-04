from __future__ import annotations

import pytest
from fastapi import FastAPI, Request

from rate_limiter import FixedWindow, rate_limit


@pytest.mark.asyncio
async def test_handler_with_postponed_annotations(redis, client_for):
    app = FastAPI()
    limiter = FixedWindow(redis=redis, limit=2, window=60)

    @app.get("/items/{item_id}")
    @rate_limit(limiter)
    async def item(item_id: int, q: str | None = None) -> dict[str, object]:
        return {"id": item_id, "q": q}

    @app.get("/who")
    @rate_limit(limiter, namespace="who")
    async def who(request: Request) -> dict[str, str]:
        return {"path": request.url.path}

    async with client_for(app) as c:
        ok = await c.get("/items/5?q=y")
        bad = await c.get("/items/abc")
        who_response = await c.get("/who")

    assert ok.json() == {"id": 5, "q": "y"}
    assert ok.headers["X-RateLimit-Remaining"] == "1"
    assert bad.status_code == 422
    assert who_response.json() == {"path": "/who"}
