from collections.abc import Callable
from functools import wraps

from fastapi import Request, Response

from rate_limiter.algorithms.base import RateLimiter


def rate_limit(
    limiter: RateLimiter,
    key_func: Callable[[Request], str] | None = None,
):
    if key_func is None:
        key_func = lambda request: request.client.host

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")

            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise RuntimeError(
                    "rate_limit decorator requires a Request parameter"
                )

            key = key_func(request)

            result = await limiter.allow(key)

            if not result.allowed:
                return Response(
                    content="Too Many Requests",
                    status_code=429,
                    headers={
                        "X-RateLimit-Limit": str(result.limit),
                        "X-RateLimit-Remaining": str(result.remaining),
                        "X-RateLimit-Reset": str(result.reset_after),
                        "Retry-After": str(result.reset_after),
                    },
                )

            response = await func(*args, **kwargs)

            if isinstance(response, Response):
                response.headers["X-RateLimit-Limit"] = str(result.limit)
                response.headers["X-RateLimit-Remaining"] = str(
                    result.remaining
                )
                response.headers["X-RateLimit-Reset"] = str(
                    result.reset_after
                )

            return response

        return wrapper

    return decorator