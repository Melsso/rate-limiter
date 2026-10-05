import pytest

from rate_limiter import FixedWindow


@pytest.mark.asyncio
async def test_fixed_window_allows_within_limit(redis):
    limiter = FixedWindow(
        redis=redis,
        limit=3,
        window=60,
    )

    assert (await limiter.allow("user")).allowed
    assert (await limiter.allow("user")).allowed
    assert (await limiter.allow("user")).allowed


@pytest.mark.asyncio
async def test_fixed_window_blocks_after_limit(redis):
    limiter = FixedWindow(
        redis=redis,
        limit=3,
        window=60,
    )

    await limiter.allow("user")
    await limiter.allow("user")
    await limiter.allow("user")

    result = await limiter.allow("user")

    assert result.allowed is False
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_fixed_window_denied_requests_do_not_increment_counter(redis):
    limiter = FixedWindow(redis=redis, limit=3, window=60)

    for _ in range(10):
        await limiter.allow("user")

    assert await redis.get("rl:fw:user") == "3"
    assert await redis.ttl("rl:fw:user") > 0
