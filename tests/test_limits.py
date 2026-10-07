import pytest
from redis.asyncio import Redis

from rate_limiter import (
    FixedWindow,
    MemoryFixedWindow,
    MemorySlidingWindow,
    MemoryTokenBucket,
    SlidingWindow,
    TokenBucket,
)
from rate_limiter.limits import parse_limit


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("5/second", (5, 1)),
        ("5/minute", (5, 60)),
        ("5/minutes", (5, 60)),
        ("100/hour", (100, 3600)),
        ("1/day", (1, 86400)),
        ("10/5 minutes", (10, 300)),
        ("10/5minutes", (10, 300)),
        (" 5 / MINUTE ", (5, 60)),
    ],
)
def test_parse_limit(spec, expected):
    assert parse_limit(spec) == expected


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "5",
        "5/",
        "/minute",
        "5/week",
        "five/minute",
        "0/minute",
        "5/0 minutes",
        "-5/minute",
        "5 per minute",
        "5/minute extra",
        "5/1.5 minutes",
        None,
        5,
    ],
)
def test_parse_limit_rejects_invalid_strings(spec):
    with pytest.raises((ValueError, TypeError)):
        parse_limit(spec)


def test_redis_limiters_from_limit():
    redis = Redis()

    fixed = FixedWindow.from_limit(redis, "5/minute", prefix="x")
    assert (fixed.limit, fixed.window, fixed.prefix) == (5, 60, "x")

    sliding = SlidingWindow.from_limit(redis, "10/5 minutes")
    assert (sliding.limit, sliding.window, sliding.prefix) == (10, 300, "rl:sw")

    bucket = TokenBucket.from_limit(redis, "5/minute")
    assert bucket.capacity == 5
    assert bucket.refill_rate == pytest.approx(5 / 60)
    assert bucket.prefix == "rl:tb"


def test_memory_limiters_from_limit():
    fixed = MemoryFixedWindow.from_limit("5/minute", max_keys=10)
    assert (fixed.limit, fixed.window, fixed.max_keys) == (5, 60, 10)

    sliding = MemorySlidingWindow.from_limit("1/hour")
    assert (sliding.limit, sliding.window) == (1, 3600)

    bucket = MemoryTokenBucket.from_limit("10/5 minutes")
    assert bucket.capacity == 10
    assert bucket.refill_rate == pytest.approx(10 / 300)


def test_from_limit_rejects_invalid_strings():
    with pytest.raises(ValueError):
        FixedWindow.from_limit(Redis(), "nonsense")
    with pytest.raises(ValueError):
        MemoryTokenBucket.from_limit("nonsense")
