import hashlib
import inspect
import ipaddress
from collections.abc import Awaitable, Callable

from starlette.requests import Request

IPV6_PREFIX = 64

_KeyFunc = Callable[[Request], str | Awaitable[str]]


def _check_prefix(ipv6_prefix: int) -> None:
    if not 1 <= ipv6_prefix <= 128:
        raise ValueError("ipv6_prefix must be between 1 and 128")


def normalize_ip(value: str, ipv6_prefix: int = IPV6_PREFIX) -> str:
    host = value.strip().split("%", 1)[0]
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return value
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/{ipv6_prefix}", strict=False))
    return str(address)


def _socket_key(request: Request, ipv6_prefix: int) -> str:
    if request.client is None:
        return "unknown"
    return normalize_ip(request.client.host, ipv6_prefix)


def default_key_func(request: Request) -> str:
    return _socket_key(request, IPV6_PREFIX)


def ip_key_func(ipv6_prefix: int = IPV6_PREFIX) -> Callable[[Request], str]:
    _check_prefix(ipv6_prefix)

    def key_func(request: Request) -> str:
        return _socket_key(request, ipv6_prefix)

    return key_func


def forwarded_key_func(
    trusted_proxies: int = 1, ipv6_prefix: int = IPV6_PREFIX
) -> Callable[[Request], str]:
    if trusted_proxies < 1:
        raise ValueError("trusted_proxies must be >= 1")
    _check_prefix(ipv6_prefix)

    def key_func(request: Request) -> str:
        header = ",".join(request.headers.getlist("x-forwarded-for"))
        if header:
            hops = [h.strip() for h in header.split(",") if h.strip()]
            if len(hops) >= trusted_proxies:
                return normalize_ip(hops[-trusted_proxies], ipv6_prefix)
        return _socket_key(request, ipv6_prefix)

    return key_func


def hashed_key_func(
    key_func: _KeyFunc, length: int = 32
) -> Callable[[Request], Awaitable[str]]:
    if not 1 <= length <= 64:
        raise ValueError("length must be between 1 and 64")

    async def hashed(request: Request) -> str:
        raw = key_func(request)
        if inspect.isawaitable(raw):
            raw = await raw
        return hashlib.sha256(str(raw).encode()).hexdigest()[:length]

    return hashed
