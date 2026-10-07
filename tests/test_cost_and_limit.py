import pytest

from rate_limiter import (
    FixedWindow,
    MemoryFixedWindow,
    MemorySlidingWindow,
    MemoryTokenBucket,
    SlidingWindow,
    TokenBucket,
)


@pytest.fixture(
    params=[
        "fixed_window",
        "sliding_window",
        "token_bucket",
        "memory_fixed_window",
        "memory_sliding_window",
        "memory_token_bucket",
    ]
)
def make_limiter(request, redis, clock):
    def factory(limit=10):
        match request.param:
            case "fixed_window":
                return FixedWindow(redis=redis, limit=limit, window=3600)
            case "sliding_window":
                return SlidingWindow(redis=redis, limit=limit, window=3600)
            case "token_bucket":
                return TokenBucket(redis=redis, capacity=limit, refill_rate=1e-6)
            case "memory_fixed_window":
                return MemoryFixedWindow(limit=limit, window=3600, clock=clock)
            case "memory_sliding_window":
                return MemorySlidingWindow(limit=limit, window=3600, clock=clock)
            case _:
                return MemoryTokenBucket(capacity=limit, refill_rate=1e-6, clock=clock)

    return factory


@pytest.mark.asyncio
async def test_cost_consumes_multiple_units(make_limiter):
    limiter = make_limiter(10)
    result = await limiter.allow("u", cost=4)
    assert result.allowed
    assert result.remaining == 6


@pytest.mark.asyncio
async def test_denied_request_does_not_consume(make_limiter):
    limiter = make_limiter(10)
    await limiter.allow("u", cost=6)

    denied = await limiter.allow("u", cost=6)

    assert not denied.allowed
    assert denied.remaining == 4
    assert (await limiter.allow("u", cost=4)).allowed


@pytest.mark.asyncio
async def test_cost_above_limit_is_denied(make_limiter):
    limiter = make_limiter(10)

    result = await limiter.allow("u", cost=11)

    assert not result.allowed
    assert result.remaining == 10
    assert result.reset_after >= 0
    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("cost", [0, -1, 1.5, True])
async def test_invalid_cost_raises(make_limiter, cost):
    limiter = make_limiter()
    with pytest.raises(ValueError):
        await limiter.allow("u", cost=cost)
    with pytest.raises(ValueError):
        await limiter.peek("u", cost=cost)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -5, 2.5, True])
async def test_invalid_limit_raises(make_limiter, limit):
    limiter = make_limiter()
    with pytest.raises(ValueError):
        await limiter.allow("u", limit=limit)
    with pytest.raises(ValueError):
        await limiter.peek("u", limit=limit)


@pytest.mark.asyncio
async def test_limit_override_applies_per_call(make_limiter):
    limiter = make_limiter(10)

    first = await limiter.allow("u", limit=2)
    assert first.allowed
    assert first.limit == 2
    assert (await limiter.allow("u", limit=2)).allowed

    third = await limiter.allow("u", limit=2)
    assert not third.allowed
    assert third.limit == 2
    assert third.remaining == 0


@pytest.mark.asyncio
async def test_fixed_window_limit_can_change_between_calls(redis):
    limiter = FixedWindow(redis=redis, limit=10, window=60)

    assert (await limiter.allow("u", limit=1)).allowed
    assert not (await limiter.allow("u", limit=1)).allowed
    assert (await limiter.allow("u", limit=2)).allowed


@pytest.mark.asyncio
async def test_token_bucket_lower_limit_clamps_stored_tokens(redis):
    limiter = TokenBucket(redis=redis, capacity=10, refill_rate=1e-6)
    await limiter.allow("u")

    result = await limiter.allow("u", limit=2)

    assert result.allowed
    assert result.limit == 2
    assert result.remaining == 1


@pytest.mark.asyncio
async def test_token_bucket_higher_limit_does_not_grant_tokens_at_once(redis):
    limiter = TokenBucket(redis=redis, capacity=2, refill_rate=1e-6)
    await limiter.allow("u")
    await limiter.allow("u")

    result = await limiter.allow("u", limit=100)

    assert not result.allowed


@pytest.mark.asyncio
async def test_token_bucket_refill_rate_scales_with_limit(redis):
    limiter = TokenBucket(redis=redis, capacity=10, refill_rate=1)
    assert (await limiter.allow("u", cost=5, limit=5)).allowed

    blocked = await limiter.allow("u", limit=5)

    assert not blocked.allowed
    assert blocked.reset_after == 2


@pytest.mark.asyncio
async def test_peek_does_not_consume(make_limiter):
    limiter = make_limiter(3)

    for _ in range(5):
        peeked = await limiter.peek("u")
        assert peeked.allowed
        assert peeked.remaining == 3


@pytest.mark.asyncio
async def test_peek_reflects_consumed_state(make_limiter):
    limiter = make_limiter(3)
    await limiter.allow("u")
    await limiter.allow("u")

    peeked = await limiter.peek("u")
    assert peeked.allowed
    assert peeked.remaining == 1

    await limiter.allow("u")
    blocked = await limiter.peek("u")
    assert not blocked.allowed
    assert blocked.remaining == 0
    assert not (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_peek_with_cost_and_limit(make_limiter):
    limiter = make_limiter(10)

    assert (await limiter.peek("u", cost=10)).allowed
    assert not (await limiter.peek("u", cost=11)).allowed
    assert not (await limiter.peek("u", cost=3, limit=2)).allowed


@pytest.mark.asyncio
async def test_peek_does_not_create_keys(make_limiter, redis):
    await make_limiter().peek("u")

    assert await redis.keys("rl:*") == []


@pytest.mark.asyncio
async def test_reset_clears_state(make_limiter):
    limiter = make_limiter(1)
    assert (await limiter.allow("u")).allowed
    assert not (await limiter.allow("u")).allowed

    await limiter.reset("u")

    assert (await limiter.allow("u")).allowed


@pytest.mark.asyncio
async def test_reset_only_affects_the_given_key(make_limiter):
    limiter = make_limiter(1)
    await limiter.allow("a")
    await limiter.allow("b")

    await limiter.reset("a")

    assert (await limiter.allow("a")).allowed
    assert not (await limiter.allow("b")).allowed


@pytest.mark.asyncio
async def test_reset_unknown_key_is_a_noop(make_limiter):
    await make_limiter().reset("never-seen")
