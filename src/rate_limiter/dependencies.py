from collections.abc import Callable

from fastapi import Request, Response

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core.guard import Guard, IntOrFunc, KeyFunc
from rate_limiter.core.health import DEFAULT_COOLDOWN
from rate_limiter.core.response import rate_limit_headers
from rate_limiter.exceptions import RateLimitExceeded
from rate_limiter.keys import default_key_func


class RateLimit:
    def __init__(
        self,
        limiter: RateLimiter,
        key_func: KeyFunc = default_key_func,
        fail_open: bool = True,
        namespace: str | None = None,
        exempt_when: Callable[[Request], bool] | None = None,
        cost: IntOrFunc = 1,
        limit: IntOrFunc | None = None,
        fallback: RateLimiter | None = None,
        cooldown: float = DEFAULT_COOLDOWN,
    ) -> None:
        self.guard = Guard(
            limiter,
            key_func=key_func,
            fail_open=fail_open,
            namespace=namespace,
            exempt_when=exempt_when,
            cost=cost,
            limit=limit,
            fallback=fallback,
            cooldown=cooldown,
        )

    async def evaluate(self, request: Request, response: Response) -> dict[str, str]:
        result = await self.guard.check(request)

        if result is None:
            return {}
        if not result.allowed:
            raise RateLimitExceeded(result)

        headers = rate_limit_headers(result)
        response.headers.update(headers)
        return headers

    async def __call__(self, request: Request, response: Response) -> None:
        await self.evaluate(request, response)
