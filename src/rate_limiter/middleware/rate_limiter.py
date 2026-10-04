from collections.abc import Callable, Iterable

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core.guard import Guard, KeyFunc, RateLimiterUnavailable
from rate_limiter.core.response import rate_limit_headers, too_many_requests_response
from rate_limiter.keys import default_key_func


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter,
        key_func: KeyFunc = default_key_func,
        fail_open: bool = True,
        exempt_when: Callable[[Request], bool] | None = None,
        exclude_paths: Iterable[str] = (),
        exclude_methods: Iterable[str] = ("OPTIONS",),
    ) -> None:
        self.app = app
        self.guard = Guard(
            limiter,
            key_func=key_func,
            fail_open=fail_open,
            exempt_when=exempt_when,
        )
        self.exclude_paths = frozenset(exclude_paths)
        self.exclude_methods = frozenset(m.upper() for m in exclude_methods)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in self.exclude_methods
            or scope["path"] in self.exclude_paths
        ):
            await self.app(scope, receive, send)
            return

        try:
            result = await self.guard.check(Request(scope))
        except RateLimiterUnavailable:
            response = Response("Rate limiter unavailable", status_code=503)
            await response(scope, receive, send)
            return

        if result is None:
            await self.app(scope, receive, send)
            return

        if not result.allowed:
            await too_many_requests_response(result)(scope, receive, send)
            return

        headers = rate_limit_headers(result)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(headers)
            await send(message)

        await self.app(scope, receive, send_with_headers)
