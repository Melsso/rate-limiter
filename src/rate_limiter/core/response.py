from fastapi import Response

from rate_limiter.schemas import RateLimitResult


def rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_after),
    }


def too_many_requests_response(
    result: RateLimitResult,
) -> Response:
    headers = rate_limit_headers(result)

    headers["Retry-After"] = str(result.reset_after)

    return Response(
        content="Too Many Requests",
        status_code=429,
        headers=headers,
    )