from starlette.responses import JSONResponse, Response

from rate_limiter.schemas import RateLimitResult


def rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_after),
    }


def rejection_headers(result: RateLimitResult) -> dict[str, str]:
    headers = rate_limit_headers(result)
    headers["Retry-After"] = str(max(1, result.reset_after))
    return headers


def too_many_requests_response(result: RateLimitResult) -> Response:
    return JSONResponse(
        {"detail": "Too Many Requests"},
        status_code=429,
        headers=rejection_headers(result),
    )
