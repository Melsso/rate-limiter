import pytest

from rate_limiter import TokenBucket


@pytest.mark.asyncio
async def test_token_bucket_consumes_tokens(redis):
    limiter = TokenBucket(
        redis=redis,
        capacity=2,
        refill_rate=1,
    )

    assert (await limiter.allow("user")).allowed
    assert (await limiter.allow("user")).allowed

    result = await limiter.allow("user")

    assert result.allowed is False