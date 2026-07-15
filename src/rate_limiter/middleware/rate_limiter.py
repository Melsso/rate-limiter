from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core.response import rate_limit_headers, too_many_requests_response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter,
    ):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        key = request.client.host if request.client else "unknown"

        result = await self.limiter.allow(key)

        if not result.allowed:
            return too_many_requests_response(result)

        response = await call_next(request)

        response.headers.update(rate_limit_headers(result))

        return response
