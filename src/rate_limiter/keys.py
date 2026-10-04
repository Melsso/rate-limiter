from collections.abc import Callable

from starlette.requests import Request


def default_key_func(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def forwarded_key_func(trusted_proxies: int = 1) -> Callable[[Request], str]:
    """Client IP from X-Forwarded-For, counting `trusted_proxies` hops from the right.

    With one proxy that appends the peer address (Nginx's
    $proxy_add_x_forwarded_for), the last entry is the real client.
    Entries further left are client-controlled and ignored.
    """

    def key_func(request: Request) -> str:
        header = request.headers.get("x-forwarded-for")
        if header:
            hops = [h.strip() for h in header.split(",") if h.strip()]
            if len(hops) >= trusted_proxies:
                return hops[-trusted_proxies]
        return default_key_func(request)

    return key_func
