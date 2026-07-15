from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from fastapi import Request, Response

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core.response import rate_limit_headers, too_many_requests_response


def rate_limit(
    limiter: RateLimiter,
    key_func: Callable[[Request], str] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    if key_func is None:

        def key_func(request: Request) -> str:
            return request.client.host if request.client else "unknown"

    def decorator(
        func: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = kwargs.get("request")

            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise RuntimeError("rate_limit decorator requires a Request parameter")

            key = key_func(request)

            result = await limiter.allow(key)

            if not result.allowed:
                return too_many_requests_response(result)

            response = await func(*args, **kwargs)

            if isinstance(response, Response):
                response.headers.update(rate_limit_headers(result))

            return response

        return wrapper

    return decorator
