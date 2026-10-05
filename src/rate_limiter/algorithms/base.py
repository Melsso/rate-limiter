from abc import ABC, abstractmethod

from rate_limiter.schemas import RateLimitResult


def check_cost(cost: int) -> None:
    if isinstance(cost, bool) or not isinstance(cost, int) or cost < 1:
        raise ValueError("cost must be an integer >= 1")


def check_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be an integer >= 1")


class RateLimiter(ABC):
    @abstractmethod
    async def allow(
        self, key: str, cost: int = 1, limit: int | None = None
    ) -> RateLimitResult:
        """Consume `cost` units for `key` if they fit, otherwise deny.

        A denied request consumes nothing. `limit` overrides the configured
        limit for this call only.
        """

    @abstractmethod
    async def peek(
        self, key: str, cost: int = 1, limit: int | None = None
    ) -> RateLimitResult:
        """Same decision as `allow`, without consuming anything.

        `allowed` tells whether a request of this cost would pass right now.
        """

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Forget all state for `key`.

        `key` is the value the limiter receives, without the limiter prefix. If
        a namespace is used, it is part of the key.
        """
