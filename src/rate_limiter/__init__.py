from importlib.metadata import PackageNotFoundError, version

from rate_limiter.algorithms import (
    FixedWindow,
    MemoryFixedWindow,
    MemorySlidingWindow,
    MemoryTokenBucket,
    SlidingWindow,
    TokenBucket,
)
from rate_limiter.decorators import rate_limit
from rate_limiter.dependencies import RateLimit
from rate_limiter.exceptions import RateLimiterUnavailableError, RateLimitExceeded
from rate_limiter.keys import (
    default_key_func,
    forwarded_key_func,
    hashed_key_func,
    ip_key_func,
)
from rate_limiter.schemas import RateLimitResult

try:
    __version__ = version("rate-limiter")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "FixedWindow",
    "MemoryFixedWindow",
    "MemorySlidingWindow",
    "MemoryTokenBucket",
    "RateLimit",
    "RateLimitExceeded",
    "RateLimitResult",
    "RateLimiterUnavailableError",
    "SlidingWindow",
    "TokenBucket",
    "default_key_func",
    "forwarded_key_func",
    "hashed_key_func",
    "ip_key_func",
    "rate_limit",
]
