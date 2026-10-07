import inspect
from collections.abc import Awaitable, Callable

from redis.exceptions import RedisError
from starlette.requests import Request

from rate_limiter.algorithms.base import RateLimiter, check_cost, check_limit
from rate_limiter.core.health import (
    DEFAULT_COOLDOWN,
    get_breaker,
    warn_throttled,
)
from rate_limiter.exceptions import RateLimiterUnavailableError
from rate_limiter.keys import default_key_func
from rate_limiter.schemas import RateLimitResult

KeyFunc = Callable[[Request], str | Awaitable[str]]
IntOrFunc = int | Callable[[Request], int]


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
        cost: IntOrFunc = 1,
        limit: IntOrFunc | None = None,
        fallback: RateLimiter | None = None,
        cooldown: float = DEFAULT_COOLDOWN,
    ) -> None:
        if not callable(cost):
            check_cost(cost)
        if limit is not None and not callable(limit):
            check_limit(limit)
        if cooldown < 0:
            raise ValueError("cooldown must be >= 0")

        self.limiter = limiter
        self.key_func = key_func
        self.fail_open = fail_open
        self.namespace = namespace
        self.exempt_when = exempt_when
        self.cost = cost
        self.limit = limit
        self.fallback = fallback
        self.cooldown = cooldown
        self._breaker = get_breaker(limiter)

    async def check(self, request: Request) -> RateLimitResult | None:
        if self.exempt_when is not None and self.exempt_when(request):
            return None

        key = await resolve_key(self.key_func, request)
        if self.namespace:
            key = f"{self.namespace}:{key}"

        cost = self.cost(request) if callable(self.cost) else self.cost
        limit = self.limit(request) if callable(self.limit) else self.limit

        if not self._breaker.allow_request(self.cooldown):
            return await self._degrade(key, cost, limit, None)

        try:
            result = await self.limiter.allow(key, cost=cost, limit=limit)
        except RedisError as exc:
            self._breaker.record_failure(self.cooldown)
            return await self._degrade(key, cost, limit, exc)

        self._breaker.record_success()
        return result

    async def _degrade(
        self, key: str, cost: int, limit: int | None, exc: BaseException | None
    ) -> RateLimitResult | None:
        if self.fallback is not None:
            warn_throttled("rate limiter backend unavailable, using fallback", exc)
            return await self.fallback.allow(key, cost=cost, limit=limit)
        if not self.fail_open:
            warn_throttled("rate limiter backend unavailable, rejecting requests", exc)
            raise RateLimiterUnavailableError() from exc
        warn_throttled("rate limiter backend unavailable, failing open", exc)
        return None
