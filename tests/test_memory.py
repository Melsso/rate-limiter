import pytest

from rate_limiter import MemoryFixedWindow, MemorySlidingWindow, MemoryTokenBucket


@pytest.mark.asyncio
async def test_fixed_window_counts_and_expires(clock):
    limiter = MemoryFixedWindow(limit=2, window=60, clock=clock)

    first = await limiter.allow("u")
    assert first.allowed
    assert first.remaining == 1
    assert first.reset_after == 60
    assert (await limiter.allow("u")).allowed

    clock.advance(30)
    denied = await limiter.allow("u")
    assert not denied.allowed
    assert denied.remaining == 0
    assert denied.reset_after == 30

    clock.advance(30)
    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_sliding_window_weights_the_previous_window(clock):
    clock.now = 1000.0
    limiter = MemorySlidingWindow(limit=10, window=100, clock=clock)
    assert (await limiter.allow("u", cost=10)).allowed

    clock.advance(100)
    full_weight = await limiter.allow("u")
    assert not full_weight.allowed
    assert full_weight.reset_after >= 1

    clock.advance(50)
    assert not (await limiter.peek("u", cost=6)).allowed
    assert (await limiter.peek("u", cost=5)).allowed
    assert (await limiter.allow("u", cost=5)).allowed
    assert not (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_sliding_window_discards_state_older_than_a_window(clock):
    clock.now = 1000.0
    limiter = MemorySlidingWindow(limit=10, window=100, clock=clock)
    await limiter.allow("u", cost=10)

    clock.advance(1000)

    assert (await limiter.allow("u", cost=10)).allowed


@pytest.mark.asyncio
async def test_token_bucket_refills_and_is_capped(clock):
    limiter = MemoryTokenBucket(capacity=10, refill_rate=1, clock=clock)
    assert (await limiter.allow("u", cost=10)).allowed

    denied = await limiter.allow("u")
    assert not denied.allowed
    assert denied.reset_after == 1

    clock.advance(3)
    assert (await limiter.allow("u", cost=3)).allowed
    assert not (await limiter.peek("u")).allowed

    clock.advance(10_000)
    result = await limiter.allow("u")
    assert result.allowed
    assert result.remaining == 9


@pytest.mark.asyncio
async def test_token_bucket_refill_rate_scales_with_limit(clock):
    limiter = MemoryTokenBucket(capacity=10, refill_rate=1, clock=clock)
    assert (await limiter.allow("u", cost=5, limit=5)).allowed

    blocked = await limiter.allow("u", limit=5)

    assert not blocked.allowed
    assert blocked.reset_after == 2


@pytest.mark.asyncio
async def test_least_recently_used_keys_are_evicted(clock):
    limiter = MemoryFixedWindow(limit=1, window=60, max_keys=2, clock=clock)
    await limiter.allow("a")
    await limiter.allow("b")
    assert not (await limiter.allow("a")).allowed

    await limiter.allow("c")

    assert len(limiter) == 2
    assert not (await limiter.allow("a")).allowed
    assert (await limiter.allow("b")).allowed


@pytest.mark.asyncio
async def test_memory_stays_bounded(clock):
    limiter = MemoryTokenBucket(capacity=5, refill_rate=1, max_keys=100, clock=clock)
    for i in range(1000):
        await limiter.allow(f"client-{i}")

    assert len(limiter) == 100


@pytest.mark.parametrize(
    "factory",
    [
        lambda: MemoryFixedWindow(limit=0, window=60),
        lambda: MemoryFixedWindow(limit=1, window=0),
        lambda: MemoryFixedWindow(limit=1, window=60, max_keys=0),
        lambda: MemorySlidingWindow(limit=0, window=60),
        lambda: MemorySlidingWindow(limit=1, window=0),
        lambda: MemoryTokenBucket(capacity=0, refill_rate=1),
        lambda: MemoryTokenBucket(capacity=1, refill_rate=0),
    ],
)
def test_invalid_arguments_raise(factory):
    with pytest.raises(ValueError):
        factory()
