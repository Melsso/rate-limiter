from collections.abc import Awaitable, Callable, Iterable

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core.guard import Guard, IntOrFunc, KeyFunc
from rate_limiter.core.health import DEFAULT_COOLDOWN
from rate_limiter.core.response import (
    rate_limit_headers,
    rejection_headers,
    too_many_requests_response,
)
from rate_limiter.exceptions import RateLimiterUnavailableError
from rate_limiter.keys import default_key_func
from rate_limiter.schemas import RateLimitResult

OnLimit = Callable[[Request, RateLimitResult], Response | Awaitable[Response]]
OnUnavailable = Callable[[Request], Response | Awaitable[Response]]


def _default_on_limit(request: Request, result: RateLimitResult) -> Response:
    return too_many_requests_response(result)


def _default_on_unavailable(request: Request) -> Response:
    return JSONResponse({"detail": "Rate limiter unavailable"}, status_code=503)


async def _resolve(value: Response | Awaitable[Response]) -> Response:
    if isinstance(value, Response):
        return value
    return await value


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
        cost: IntOrFunc = 1,
        limit: IntOrFunc | None = None,
        fallback: RateLimiter | None = None,
        cooldown: float = DEFAULT_COOLDOWN,
        on_limit: OnLimit | None = None,
        on_unavailable: OnUnavailable | None = None,
    ) -> None:
        self.app = app
        self.guard = Guard(
            limiter,
            key_func=key_func,
            fail_open=fail_open,
            exempt_when=exempt_when,
            cost=cost,
            limit=limit,
            fallback=fallback,
            cooldown=cooldown,
        )
        self.exclude_paths = frozenset(exclude_paths)
        self.exclude_methods = frozenset(m.upper() for m in exclude_methods)
        self.on_limit: OnLimit = on_limit or _default_on_limit
        self.on_unavailable: OnUnavailable = on_unavailable or _default_on_unavailable

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in self.exclude_methods
            or scope["path"] in self.exclude_paths
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        try:
            result = await self.guard.check(request)
        except RateLimiterUnavailableError:
            response = await _resolve(self.on_unavailable(request))
            await response(scope, receive, send)
            return

        if result is None:
            await self.app(scope, receive, send)
            return

        if not result.allowed:
            response = await _resolve(self.on_limit(request, result))
            for name, value in rejection_headers(result).items():
                response.headers.setdefault(name, value)
            await response(scope, receive, send)
            return

        headers = rate_limit_headers(result)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(headers)
            await send(message)

        await self.app(scope, receive, send_with_headers)
