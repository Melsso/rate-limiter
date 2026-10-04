from importlib.metadata import PackageNotFoundError, version

from rate_limiter.algorithms import FixedWindow, SlidingWindow, TokenBucket
from rate_limiter.decorators import rate_limit
from rate_limiter.dependencies import RateLimit
from rate_limiter.keys import default_key_func, forwarded_key_func
from rate_limiter.schemas import RateLimitResult

try:
    __version__ = version("rate-limiter")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "FixedWindow",
    "RateLimit",
    "RateLimitResult",
    "SlidingWindow",
    "TokenBucket",
    "default_key_func",
    "forwarded_key_func",
    "rate_limit",
]
