import pytest

from rate_limiter import SlidingWindow


@pytest.mark.asyncio
async def test_sliding_window_blocks_after_limit(redis):
    limiter = SlidingWindow(
        redis=redis,
        limit=2,
        window=60,
    )

    assert (await limiter.allow("user")).allowed
    assert (await limiter.allow("user")).allowed

    result = await limiter.allow("user")

    assert result.allowed is False
