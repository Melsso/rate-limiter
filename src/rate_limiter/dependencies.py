from collections.abc import Callable

from fastapi import HTTPException, Request, Response

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core.guard import Guard, KeyFunc, RateLimiterUnavailable
from rate_limiter.core.response import rate_limit_headers, rejection_headers
from rate_limiter.keys import default_key_func


class RateLimit:
    def __init__(
        self,
        limiter: RateLimiter,
        key_func: KeyFunc = default_key_func,
        fail_open: bool = True,
        namespace: str | None = None,
        exempt_when: Callable[[Request], bool] | None = None,
    ) -> None:
        self.guard = Guard(
            limiter,
            key_func=key_func,
            fail_open=fail_open,
            namespace=namespace,
            exempt_when=exempt_when,
        )

    async def evaluate(self, request: Request, response: Response) -> dict[str, str]:
        try:
            result = await self.guard.check(request)
        except RateLimiterUnavailable as exc:
            raise HTTPException(503, "Rate limiter unavailable") from exc

        if result is None:
            return {}
        if not result.allowed:
            raise HTTPException(
                429, "Too Many Requests", headers=rejection_headers(result)
            )

        headers = rate_limit_headers(result)
        response.headers.update(headers)
        return headers

    async def __call__(self, request: Request, response: Response) -> None:
        await self.evaluate(request, response)
