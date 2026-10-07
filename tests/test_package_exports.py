import rate_limiter


def test_public_exports():
    expected = {
        "FixedWindow",
        "MemoryFixedWindow",
        "MemorySlidingWindow",
        "MemoryTokenBucket",
        "RateLimit",
        "RateLimitExceeded",
        "RateLimitResult",
        "RateLimiterUnavailableError",
        "SlidingWindow",
        "TokenBucket",
        "default_key_func",
        "forwarded_key_func",
        "hashed_key_func",
        "ip_key_func",
        "rate_limit",
    }
    assert set(rate_limiter.__all__) == expected
    for name in expected:
        assert hasattr(rate_limiter, name)
