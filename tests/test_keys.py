import hashlib

import pytest
from starlette.requests import Request

from rate_limiter import (
    default_key_func,
    forwarded_key_func,
    hashed_key_func,
    ip_key_func,
)


def make_request(headers=None, client=("9.9.9.9", 1)):
    scope = {
        "type": "http",
        "headers": [(k.encode(), v.encode()) for k, v in (headers or [])],
        "client": client,
    }
    return Request(scope)


def test_default_key_func_leaves_ipv4_alone():
    request = make_request(client=("203.0.113.7", 1))
    assert default_key_func(request) == "203.0.113.7"


def test_default_key_func_groups_ipv6_by_64():
    same_a = make_request(client=("2001:db8:1:2::1", 1))
    same_b = make_request(client=("2001:db8:1:2:ffff:ffff:ffff:ffff", 1))
    other = make_request(client=("2001:db8:1:3::1", 1))
    assert default_key_func(same_a) == "2001:db8:1:2::/64"
    assert default_key_func(same_b) == "2001:db8:1:2::/64"
    assert default_key_func(other) == "2001:db8:1:3::/64"


def test_default_key_func_unwraps_ipv4_mapped_addresses():
    request = make_request(client=("::ffff:203.0.113.7", 1))
    assert default_key_func(request) == "203.0.113.7"


def test_default_key_func_ignores_ipv6_zone_id():
    request = make_request(client=("fe80::1%eth0", 1))
    assert default_key_func(request) == "fe80::/64"


def test_default_key_func_passes_non_ip_hosts_through():
    request = make_request(client=("testclient", 1))
    assert default_key_func(request) == "testclient"


def test_default_key_func_without_client():
    assert default_key_func(make_request(client=None)) == "unknown"


def test_ip_key_func_custom_prefix():
    key_func = ip_key_func(ipv6_prefix=48)
    request = make_request(client=("2001:db8:1:2::1", 1))
    assert key_func(request) == "2001:db8:1::/48"


@pytest.mark.parametrize("prefix", [0, 129])
def test_invalid_ipv6_prefix_raises(prefix):
    with pytest.raises(ValueError):
        ip_key_func(ipv6_prefix=prefix)
    with pytest.raises(ValueError):
        forwarded_key_func(1, ipv6_prefix=prefix)


def test_forwarded_key_func_normalizes_ipv6_hops():
    key_func = forwarded_key_func(1)
    request = make_request([("x-forwarded-for", "evil, 2001:db8:1:2::5")])
    assert key_func(request) == "2001:db8:1:2::/64"


def test_forwarded_key_func_falls_back_to_socket_address():
    key_func = forwarded_key_func(1)
    request = make_request(client=("2001:db8::1", 1))
    assert key_func(request) == "2001:db8::/64"


def test_forwarded_key_func_reads_every_header_line():
    key_func = forwarded_key_func(1)
    request = make_request(
        [("x-forwarded-for", "6.6.6.6"), ("x-forwarded-for", "1.2.3.4")]
    )
    assert key_func(request) == "1.2.3.4"


def test_forwarded_key_func_rejects_zero_trusted_proxies():
    with pytest.raises(ValueError):
        forwarded_key_func(0)


@pytest.mark.asyncio
async def test_hashed_key_func_accepts_sync_and_async_key_funcs():
    request = make_request([("x-api-key", "secret-token")])
    expected = hashlib.sha256(b"secret-token").hexdigest()[:32]

    def sync_key(r):
        return r.headers["x-api-key"]

    async def async_key(r):
        return r.headers["x-api-key"]

    assert await hashed_key_func(sync_key)(request) == expected
    assert await hashed_key_func(async_key)(request) == expected


@pytest.mark.asyncio
async def test_hashed_key_func_bounds_length_and_hides_value():
    def key_func(r):
        return r.headers["x-api-key"]

    long_value = "x" * 10_000
    request = make_request([("x-api-key", long_value)])
    other = make_request([("x-api-key", long_value + "y")])
    hashed = hashed_key_func(key_func, length=16)

    key = await hashed(request)
    assert len(key) == 16
    assert long_value not in key
    assert key != await hashed(other)


@pytest.mark.parametrize("length", [0, 65])
def test_hashed_key_func_rejects_invalid_length(length):
    with pytest.raises(ValueError):
        hashed_key_func(lambda r: "k", length=length)
