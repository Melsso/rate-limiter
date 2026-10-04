import asyncio

import pytest

from rate_limiter import FixedWindow, SlidingWindow, TokenBucket


@pytest.mark.asyncio
async def test_fixed_window_concurrency(redis):
    limiter = FixedWindow(redis=redis, limit=10, window=60)
    results = await asyncio.gather(*(limiter.allow("u") for _ in range(50)))
    assert sum(r.allowed for r in results) == 10


@pytest.mark.asyncio
async def test_sliding_window_concurrency(redis):
    limiter = SlidingWindow(redis=redis, limit=10, window=60)
    results = await asyncio.gather(*(limiter.allow("u") for _ in range(50)))
    assert sum(r.allowed for r in results) == 10


@pytest.mark.asyncio
async def test_token_bucket_concurrency(redis):
    limiter = TokenBucket(redis=redis, capacity=10, refill_rate=0.001)
    results = await asyncio.gather(*(limiter.allow("u") for _ in range(50)))
    assert sum(r.allowed for r in results) == 10


@pytest.mark.asyncio
async def test_fixed_window_resets_after_window(redis):
    limiter = FixedWindow(redis=redis, limit=1, window=1)
    assert (await limiter.allow("u")).allowed
    assert not (await limiter.allow("u")).allowed
    await asyncio.sleep(1.2)
    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_sliding_window_recovers_after_two_windows(redis):
    limiter = SlidingWindow(redis=redis, limit=1, window=1)
    assert (await limiter.allow("u")).allowed
    assert not (await limiter.allow("u")).allowed
    await asyncio.sleep(2.2)
    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_token_bucket_refills(redis):
    limiter = TokenBucket(redis=redis, capacity=1, refill_rate=10)
    assert (await limiter.allow("u")).allowed
    await asyncio.sleep(0.3)
    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_token_bucket_reset_after_is_time_to_next_token(redis):
    limiter = TokenBucket(redis=redis, capacity=1, refill_rate=1)
    await limiter.allow("u")
    result = await limiter.allow("u")
    assert not result.allowed
    assert result.reset_after == 1


@pytest.mark.asyncio
async def test_keys_are_isolated(redis):
    limiter = FixedWindow(redis=redis, limit=1, window=60)
    assert (await limiter.allow("a")).allowed
    assert (await limiter.allow("b")).allowed


@pytest.mark.asyncio
async def test_prefixes_do_not_share_counters(redis):
    a = FixedWindow(redis=redis, limit=1, window=60, prefix="rl:a")
    b = FixedWindow(redis=redis, limit=1, window=60, prefix="rl:b")
    assert (await a.allow("u")).allowed
    assert (await b.allow("u")).allowed


@pytest.mark.parametrize(
    "factory",
    [
        lambda r: FixedWindow(r, limit=0, window=60),
        lambda r: FixedWindow(r, limit=1, window=0),
        lambda r: SlidingWindow(r, limit=0, window=60),
        lambda r: SlidingWindow(r, limit=1, window=0),
        lambda r: TokenBucket(r, capacity=0, refill_rate=1),
        lambda r: TokenBucket(r, capacity=1, refill_rate=0),
    ],
)
def test_invalid_arguments_raise(factory):
    from redis.asyncio import Redis

    with pytest.raises(ValueError):
        factory(Redis())
