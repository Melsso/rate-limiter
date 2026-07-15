from abc import ABC, abstractmethod

from rate_limiter.schemas import RateLimitResult


class RateLimiter(ABC):
    @abstractmethod
    async def allow(self, key: str) -> RateLimitResult:
        pass
