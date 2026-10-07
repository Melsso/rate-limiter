import math

import pytest

from rate_limiter import FixedWindow, SlidingWindow, TokenBucket


@pytest.mark.asyncio
async def test_fixed_window_cost_equal_to_limit_is_allowed(redis):
    limiter = FixedWindow(redis=redis, limit=5, window=60)

    result = await limiter.allow("u", cost=5)

    assert result.allowed
    assert result.remaining == 0
    assert not (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_fixed_window_key_gets_a_ttl_within_the_window(redis):
    limiter = FixedWindow(redis=redis, limit=5, window=60)
    await limiter.allow("u")

    assert 0 < await redis.ttl("rl:fw:u") <= 60


@pytest.mark.asyncio
async def test_sliding_window_key_gets_a_ttl_within_two_windows(redis):
    limiter = SlidingWindow(redis=redis, limit=5, window=60)
    await limiter.allow("u")

    assert 0 < await redis.ttl("rl:sw:u") <= 120


@pytest.mark.asyncio
async def test_sliding_window_full_current_window_is_denied(redis):
    limiter = SlidingWindow(redis=redis, limit=5, window=3600)
    await limiter.allow("u")
    stored = int(await redis.hget("rl:sw:u", "w"))
    await redis.hset("rl:sw:u", mapping={"w": stored, "c": 5, "p": 0})

    result = await limiter.allow("u")

    assert not result.allowed
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_sliding_window_state_older_than_a_window_is_discarded(redis):
    limiter = SlidingWindow(redis=redis, limit=5, window=3600)
    await limiter.allow("u")
    stored = int(await redis.hget("rl:sw:u", "w"))
    await redis.hset("rl:sw:u", mapping={"w": stored - 5, "c": 10, "p": 10})

    result = await limiter.allow("u")

    assert result.allowed
    assert result.remaining == 4


@pytest.mark.asyncio
async def test_token_bucket_idle_time_never_exceeds_capacity(redis):
    limiter = TokenBucket(redis=redis, capacity=3, refill_rate=1)
    await limiter.allow("u")
    stored = float(await redis.hget("rl:tb:u", "ts"))
    await redis.hset("rl:tb:u", "ts", stored - 3600)

    result = await limiter.allow("u")

    assert result.allowed
    assert result.remaining == 2


@pytest.mark.asyncio
async def test_token_bucket_handles_fractional_refill(redis):
    limiter = TokenBucket(redis=redis, capacity=10, refill_rate=0.5)
    assert (await limiter.allow("u", cost=10)).allowed
    stored = float(await redis.hget("rl:tb:u", "ts"))
    await redis.hset("rl:tb:u", "ts", stored - 3)

    assert not (await limiter.peek("u", cost=2)).allowed
    assert (await limiter.peek("u", cost=1)).allowed


@pytest.mark.asyncio
async def test_token_bucket_key_ttl_covers_a_full_refill(redis):
    limiter = TokenBucket(redis=redis, capacity=3, refill_rate=1)
    await limiter.allow("u")

    assert 0 < await redis.ttl("rl:tb:u") <= math.ceil(3 / 1) + 1
