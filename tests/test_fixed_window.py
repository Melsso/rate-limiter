import pytest

from rate_limiter.algorithms.fixed_window import FixedWindow


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