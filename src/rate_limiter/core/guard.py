import inspect
import logging
import time
from collections.abc import Awaitable, Callable

from redis.exceptions import RedisError
from starlette.requests import Request

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.keys import default_key_func
from rate_limiter.schemas import RateLimitResult

logger = logging.getLogger("rate_limiter")

KeyFunc = Callable[[Request], str | Awaitable[str]]
WARN_INTERVAL = 30.0


class RateLimiterUnavailable(Exception):
    """The backend failed and fail_open is False."""


async def resolve_key(key_func: KeyFunc, request: Request) -> str:
    raw = key_func(request)
    if inspect.isawaitable(raw):
        return str(await raw)
    return str(raw)


class Guard:
    def __init__(
        self,
        limiter: RateLimiter,
        key_func: KeyFunc = default_key_func,
        fail_open: bool = True,
        namespace: str | None = None,
        exempt_when: Callable[[Request], bool] | None = None,
    ) -> None:
        self.limiter = limiter
        self.key_func = key_func
        self.fail_open = fail_open
        self.namespace = namespace
        self.exempt_when = exempt_when
        self._last_warning = float("-inf")

    async def check(self, request: Request) -> RateLimitResult | None:
        if self.exempt_when is not None and self.exempt_when(request):
            return None

        key = await resolve_key(self.key_func, request)
        if self.namespace:
            key = f"{self.namespace}:{key}"

        try:
            return await self.limiter.allow(key)
        except RedisError as exc:
            if not self.fail_open:
                raise RateLimiterUnavailable from exc
            now = time.monotonic()
            if now - self._last_warning >= WARN_INTERVAL:
                self._last_warning = now
                logger.warning(
                    "rate limiter backend unavailable, failing open", exc_info=True
                )
            return None
