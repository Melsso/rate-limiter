from rate_limiter import (
    FixedWindow,
    SlidingWindow,
    TokenBucket,
    rate_limit,
)


def test_public_exports():
    assert FixedWindow
    assert SlidingWindow
    assert TokenBucket
    assert rate_limit