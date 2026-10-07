import logging
import time
from weakref import WeakKeyDictionary

from rate_limiter.algorithms.base import RateLimiter

logger = logging.getLogger("rate_limiter")

DEFAULT_COOLDOWN = 5.0
WARN_INTERVAL = 30.0

_last_warning = float("-inf")


def _now() -> float:
    return time.monotonic()


class CircuitBreaker:
    def __init__(self) -> None:
        self._open_until = 0.0
        self._tripped = False

    def allow_request(self, cooldown: float) -> bool:
        now = _now()
        if now < self._open_until:
            return False
        if self._tripped:
            self._open_until = now + cooldown
        return True

    def record_failure(self, cooldown: float) -> None:
        self._tripped = True
        self._open_until = _now() + cooldown

    def record_success(self) -> None:
        self._tripped = False
        self._open_until = 0.0


_breakers: WeakKeyDictionary[RateLimiter, CircuitBreaker] = WeakKeyDictionary()


def get_breaker(limiter: RateLimiter) -> CircuitBreaker:
    breaker = _breakers.get(limiter)
    if breaker is None:
        breaker = _breakers[limiter] = CircuitBreaker()
    return breaker


def warn_throttled(message: str, exc: BaseException | None = None) -> None:
    global _last_warning
    now = _now()
    if now - _last_warning >= WARN_INTERVAL:
        _last_warning = now
        logger.warning(message, exc_info=exc)
