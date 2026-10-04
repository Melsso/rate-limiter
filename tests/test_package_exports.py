import rate_limiter


def test_public_exports():
    expected = {
        "FixedWindow",
        "SlidingWindow",
        "TokenBucket",
        "RateLimitResult",
        "RateLimit",
        "rate_limit",
        "default_key_func",
        "forwarded_key_func",
    }
    assert set(rate_limiter.__all__) == expected
    for name in expected:
        assert hasattr(rate_limiter, name)
