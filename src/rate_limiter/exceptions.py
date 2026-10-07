from fastapi import HTTPException

from rate_limiter.core.response import rejection_headers
from rate_limiter.schemas import RateLimitResult


class RateLimitExceeded(HTTPException):
    def __init__(self, result: RateLimitResult) -> None:
        super().__init__(
            status_code=429,
            detail="Too Many Requests",
            headers=rejection_headers(result),
        )
        self.result = result


class RateLimiterUnavailableError(HTTPException):
    def __init__(self, detail: str = "Rate limiter unavailable") -> None:
        super().__init__(status_code=503, detail=detail)
