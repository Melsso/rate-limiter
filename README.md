# Rate Limiter

A Redis-backed async rate limiter library for FastAPI applications.

Three algorithms, one API, usable as a route decorator, a dependency or a global middleware:

- Fixed Window
- Sliding Window
- Token Bucket

Built with Python 3.11+, FastAPI, Redis and Lua scripts for atomic operations.

---

## Features

- Async-first implementation
- Atomic Redis operations using Lua, so concurrent requests cannot exceed the limit
- `@rate_limit` decorator that works on `async def` and `def` handlers, with no `request` parameter needed
- `RateLimit` dependency and `RateLimitMiddleware` (pure ASGI)
- Weighted requests (`cost`) and per-call limit overrides (`limit`), for example for pricing tiers
- `peek` to read the state without consuming, and `reset` to clear a key
- `X-RateLimit-*` headers on every counted response, `Retry-After` on rejections
- Custom client identification (`key_func`, sync or async), IPv6 clients grouped by `/64`, a safe `X-Forwarded-For` helper and a key-hashing helper
- Limit strings such as `"5/minute"`
- Redis outage handling: fail-open or fail-closed, an optional in-memory fallback limiter and a circuit breaker
- Custom 429 and 503 responses
- Per-limiter key prefixes and per-route namespaces
- Works with a single Redis, Valkey and Redis Cluster
- Typed (`py.typed`)

---

## Architecture

```text
             FastAPI Application
                     |
     +---------------+---------------+
     |               |               |
 Middleware      Dependency       Decorator
     |               |               |
     +---------------+---------------+
                     |
                   Guard
 (key_func, exemptions, cost/limit, circuit breaker,
  in-memory fallback, fail-open/closed)
                     |
              RateLimiter API
         allow / peek / reset
                     |
    +----------------+----------------+
    |                |                |
Fixed Window   Sliding Window    Token Bucket
    |                |                |
    +----------------+----------------+
                     |
          Redis / Valkey / Redis Cluster
                (Lua scripts)
```

---

## Installation

Requires Python 3.11+, a Redis-compatible server, and:

- `fastapi>=0.100,<1.0`
- `starlette>=0.27,<2.0`
- `redis>=5.0.1,<8` (the Python client)

```bash
pip install git+https://github.com/Melsso/rate-limiter.git@v0.2.0
```

or with Poetry:

```bash
poetry add git+https://github.com/Melsso/rate-limiter.git@v0.2.0
```

The test suite runs in CI against Redis 5, 6, 7 and 8, Valkey 8, a 3-master Redis Cluster, and the oldest allowed versions of the dependencies above.

---

## Quick start

```python
from fastapi import FastAPI
from redis.asyncio import Redis

from rate_limiter import FixedWindow, rate_limit

redis = Redis.from_url(
    "redis://localhost:6379",
    socket_timeout=1,
    socket_connect_timeout=1,
)
limiter = FixedWindow(redis=redis, limit=100, window=60)

app = FastAPI()


@app.get("/")
@rate_limit(limiter)
async def root():
    return {"message": "hello"}
```

Every counted response carries:

```text
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 60
```

Rejected requests get `429` with `{"detail": "Too Many Requests"}` and a `Retry-After` header (seconds).

---

## Usage

### Route decorator

```python
from rate_limiter import TokenBucket, rate_limit

login_limiter = TokenBucket(redis=redis, capacity=5, refill_rate=5 / 60)


@app.post("/login")
@rate_limit(login_limiter)
async def login():
    return {"message": "logged in"}
```

- Place `@rate_limit` below the route decorator.
- Handlers do not need to declare `request` or `response`; they are injected for you. If your handler already declares them (plain or wrapped in `Annotated[...]`), they are reused.
- Works with `async def` and plain `def` handlers.
- If the handler raises `HTTPException`, the `X-RateLimit-*` headers are added to that error response too.
- Requests that fail FastAPI's validation (422) are rejected before the decorator runs and are not counted. Use the middleware if you need to count every request.
- Can be stacked. The outermost limiter is checked first, and a request it rejects does not count against the inner ones. The headers shown are those of the innermost limiter.

### Dependency

```python
from fastapi import Depends
from rate_limiter import RateLimit


@app.get("/reports", dependencies=[Depends(RateLimit(limiter))])
async def reports():
    return {"ok": True}
```

Use it on a router to cover a group of routes:

```python
router = APIRouter(dependencies=[Depends(RateLimit(limiter))])
```

If the handler raises `HTTPException`, the `X-RateLimit-*` headers are not added to that error response. Use the decorator or the middleware if you need them there.

### Middleware

```python
from rate_limiter.middleware import RateLimitMiddleware

app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
    exclude_paths=["/health"],
)
```

`OPTIONS` requests are skipped by default so CORS preflights are never limited. If you use `CORSMiddleware`, add the limiter first and CORS after it, so 429 responses still get CORS headers:

```python
app.add_middleware(RateLimitMiddleware, limiter=limiter)
app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])
```

### Limit strings

Every algorithm can be built from a string:

```python
from rate_limiter import FixedWindow, SlidingWindow, TokenBucket

FixedWindow.from_limit(redis, "100/minute")
SlidingWindow.from_limit(redis, "10/5 minutes")
TokenBucket.from_limit(redis, "5/minute")
```

Units are `second`, `minute`, `hour` and `day` (singular or plural), with an optional multiplier (`"10/5 minutes"` is 10 requests per 5 minutes). For `TokenBucket`, `"5/minute"` means capacity 5, refilled at 5 tokens per 60 seconds. Invalid strings raise `ValueError`.

---

## Options

| Option | Decorator | Dependency | Middleware | Default | Meaning |
|---|---|---|---|---|---|
| `key_func` | yes | yes | yes | client IP | Picks who is limited. Receives the `Request`, returns a `str` (sync or async) |
| `cost` | yes | yes | yes | `1` | Units one request consumes. An `int` or a `Callable[[Request], int]` |
| `limit` | yes | yes | yes | `None` | Overrides the limiter's limit. An `int` or a `Callable[[Request], int]` |
| `fail_open` | yes | yes | yes | `True` | If Redis fails, let the request through. With `False`, respond `503` |
| `fallback` | yes | yes | yes | `None` | A limiter used instead of Redis while Redis fails (see below) |
| `cooldown` | yes | yes | yes | `5.0` | Seconds to skip Redis after a failure. `0` disables the circuit breaker |
| `exempt_when` | yes | yes | yes | `None` | `Callable[[Request], bool]`; matching requests are not counted |
| `namespace` | yes | yes | no | `None` | Separates counters of routes that share one limiter |
| `exclude_paths` | no | no | yes | `()` | Exact paths that skip limiting |
| `exclude_methods` | no | no | yes | `("OPTIONS",)` | HTTP methods that skip limiting |
| `on_limit` | no | no | yes | `None` | Builds the response for a rejected request (see below) |
| `on_unavailable` | no | no | yes | `None` | Builds the response when the limiter is unavailable and `fail_open` is off |

Each limiter also takes a `prefix` (`rl:fw`, `rl:sw` and `rl:tb` by default). Keys are stored as `<prefix>:<key>`. Give each limiter its own prefix, or use `namespace`, otherwise routes sharing a limiter share counters.

```python
@app.get("/a")
@rate_limit(limiter, namespace="a")
async def a(): ...


@app.get("/b")
@rate_limit(limiter, namespace="b")
async def b(): ...
```

### Cost and per-call limits

```python
def cost_from_query(request):
    return int(request.query_params.get("n", "1"))


def tier_limit(request):
    return 1000 if request.headers.get("x-tier") == "pro" else 100


@app.get("/export")
@rate_limit(limiter, cost=cost_from_query, limit=tier_limit)
async def export(): ...
```

- A request is allowed only if its whole cost fits. A denied request consumes nothing, for all three algorithms.
- A request whose cost is larger than the limit is always denied. Its `Retry-After` is not meaningful, because waiting never helps.
- `cost` and `limit` must be integers of at least 1 (booleans are rejected). Static values are checked when the decorator, dependency or middleware is created. A callable that returns an invalid value raises `ValueError` while handling the request, which becomes a 500.
- For `TokenBucket`, `limit` replaces the capacity and the refill rate is scaled by the same factor, so the time to refill from empty stays the same. Lowering the limit clamps the stored tokens at once. Raising it does not grant tokens at once; the bucket refills toward the new capacity.
- Window limiters apply the limit passed on each call to the counter already stored, so a client that moves between limits keeps its count.

### Identifying clients

The default key is the socket's client IP:

- IPv4 addresses are used as is.
- IPv6 addresses are grouped by their `/64` network (for example `2001:db8:1:2::/64`), because one client usually controls a whole `/64` and could otherwise rotate addresses to dodge the limit. Use `ip_key_func(ipv6_prefix=...)` to pick another prefix length.
- IPv4-mapped IPv6 addresses (`::ffff:a.b.c.d`) are treated as IPv4.
- Behind a reverse proxy, the socket IP is the proxy's, so all users share one limit.
- Behind a unix socket, `request.client` is `None` and everyone shares the key `"unknown"`.

If you run uvicorn behind a proxy, use `--proxy-headers --forwarded-allow-ips=<proxy ip>`, or use the helper:

```python
from rate_limiter import forwarded_key_func


@app.get("/")
@rate_limit(limiter, key_func=forwarded_key_func(trusted_proxies=1))
async def root(): ...
```

`forwarded_key_func` counts hops from the right of `X-Forwarded-For` (all header lines are joined in order), so entries a client adds on its own are ignored. `trusted_proxies` must be at least 1. It is only safe when your proxy appends the real peer address (Nginx: `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`). The selected address is normalised the same way as the default key.

Limiting by user or API key:

```python
from rate_limiter import default_key_func, hashed_key_func


def by_user(request):
    # request.state.user_id must be set by your own authentication step.
    user_id = getattr(request.state, "user_id", None)
    return f"user:{user_id}" if user_id else default_key_func(request)


async def by_api_key(request):
    # Only use this once the key has been verified.
    return request.state.api_key


@app.get("/")
@rate_limit(limiter, key_func=hashed_key_func(by_api_key))
async def root(): ...
```

Only key on a value you have validated. If the client can choose the value freely (for example any `X-API-Key` header), it can mint unlimited identities, which bypasses the limit and creates a Redis key per value. `hashed_key_func` bounds the key to a fixed length and keeps raw secrets such as API keys out of Redis key names, but it does not make an unvalidated value safe.

### Peek and reset

`peek` and `reset` are methods of the limiters. They are not exposed by the decorator, the dependency or the middleware.

```python
status = await limiter.peek("user-1")  # nothing is consumed
status.allowed, status.remaining, status.reset_after

await limiter.reset("user-1")  # forget this key
```

- `peek(key, cost=1, limit=None)` reports whether a request of that cost would pass right now, and what remains. For `FixedWindow`, a key without a counter reports `reset_after=0`.
- `reset(key)` takes the key as the limiter receives it, without the `prefix`. If you use `namespace`, include it: `await limiter.reset("a:user-1")`.

---

## When Redis is down

Any Redis error, including `RedisClusterException`, counts as a backend failure. What happens next, in order:

1. If a `fallback` limiter is set, it decides.
2. Otherwise, with `fail_open=True` (default) the request passes through. With `fail_open=False`, the request gets `503`.

Redis-py waits forever by default, so create your client with `socket_timeout` and `socket_connect_timeout` (as in the quick start). Without them nothing fails, the request just hangs.

### Circuit breaker

After a failure, requests skip Redis for `cooldown` seconds (default 5) instead of waiting for a timeout every time. When the cooldown ends, a single request probes Redis while the others keep staying away. A successful probe closes the breaker. `cooldown=0` turns the breaker off. The breaker belongs to the limiter object, so every route that shares one limiter shares one breaker.

### In-memory fallback

```python
from rate_limiter import FixedWindow, MemoryFixedWindow, rate_limit

limiter = FixedWindow(redis=redis, limit=100, window=60)
fallback = MemoryFixedWindow(limit=100, window=60)


@app.get("/")
@rate_limit(limiter, fallback=fallback)
async def root(): ...
```

`MemoryFixedWindow`, `MemorySlidingWindow` and `MemoryTokenBucket` take the same arguments as the Redis limiters, minus `redis`, and have `from_limit` too.

- **Per process:** state is not shared. With N workers a client can use N times the limit while Redis is down.
- **Configure it yourself:** give the fallback the same numbers as the primary limiter. A per-call `limit` override is passed to it as well.
- **Bounded memory:** at most `max_keys` clients are tracked (default 100,000). Beyond that, the least recently used are forgotten, which errs toward allowing. A key that keeps being denied counts as recently used.
- **Thread-safe**, with no I/O.
- **Redis counters stay separate:** when Redis returns, its own counters are used again, and nothing is copied back from the fallback.

### Logging

Failures are logged on the `rate_limiter` logger as warnings, at most once every 30 seconds per process.

---

## Custom 429 and 503 responses

The decorator and the dependency raise `RateLimitExceeded` (429, with the limiter's decision in `.result`) and `RateLimiterUnavailableError` (503). Both are `HTTPException` subclasses, so the default behaviour is a normal FastAPI error response. Register exception handlers to change it:

```python
from fastapi.responses import JSONResponse
from rate_limiter import RateLimitExceeded


@app.exception_handler(RateLimitExceeded)
async def too_many(request, exc):
    return JSONResponse(
        {"error": "slow down", "retry_in": exc.result.reset_after},
        status_code=429,
        headers=exc.headers,
    )
```

The middleware runs outside FastAPI's exception handlers, so it takes callbacks instead (sync or async, returning a `Response`):

```python
from starlette.responses import PlainTextResponse

app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
    on_limit=lambda request, result: PlainTextResponse("slow down", status_code=429),
)
```

The standard `X-RateLimit-*` and `Retry-After` headers are added to an `on_limit` response unless it already sets them. `on_unavailable(request)` works the same way for the 503.

---

## Algorithms

### Fixed Window

`FixedWindow(redis, limit, window, prefix="rl:fw")`

Counts requests inside fixed time intervals.

```text
12:00:00 - 12:01:00
limit: 100 requests
```

Pros:
- Simple
- Fast

Cons:
- Boundary bursts possible (up to 2x the limit across a window edge)

### Sliding Window

`SlidingWindow(redis, limit, window, prefix="rl:sw")`

Weights the previous window's count by how much of it still overlaps the sliding window, and adds the current window's count.

Pros:
- Smoother limiting
- Avoids fixed window boundary spikes

Cons:
- An approximation, not an exact log of requests
- With `limit=1`, a client can be blocked for almost two windows. `Retry-After` reports the real wait.

### Token Bucket

`TokenBucket(redis, capacity, refill_rate, prefix="rl:tb")`

A bucket of up to `capacity` tokens that refills at `refill_rate` tokens per second. Each request takes `cost` tokens (1 by default). `5 / 60` means five tokens per minute.

Pros:
- Allows controlled bursts
- Common in production systems

Cons:
- More state to reason about

Invalid arguments (`limit`, `window`, `capacity` below 1, or `refill_rate` of 0 or less) raise `ValueError`.

### Custom limiters

`RateLimiter` is an abstract class. A subclass implements `allow(key, cost, limit)`, `peek(key, cost, limit)` and `reset(key)`, and can be passed anywhere a limiter is accepted, including as a `fallback`.

---

## Redis atomicity and compatibility

All algorithms run as Lua scripts, so each check-and-update is a single atomic step.

```text
Request
   |
   v
Redis Lua Script
   |
   +-- read state
   |
   +-- decide allow/deny, update counters
   |
   +-- set expiration
   |
   v
Result
```

- The sliding window and token bucket use the Redis server clock (`TIME`), so clock skew between application servers does not matter.
- Each script touches a single Redis key per client and limiter, so it works on Redis Cluster. Pass a `redis.asyncio.cluster.RedisCluster` client wherever a `Redis` client is accepted.
- Keys expire on their own; nothing needs cleaning up. Memory use is bounded by the request rate times the key lifetime (`window` for fixed window, `2 * window` for sliding window, about `capacity / refill_rate` seconds for token bucket).

---

## Response format

| Situation | Status | Headers | Body |
|---|---|---|---|
| Allowed | handler's | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` | handler's |
| Rejected | 429 | the three above + `Retry-After` | `{"detail": "Too Many Requests"}` |
| Redis down, `fail_open=False`, no fallback | 503 | none | `{"detail": "Rate limiter unavailable"}` |

Rate limit headers are only added to requests that were counted. They are absent when the request is exempt, excluded, fails validation (422), or Redis failed with `fail_open=True` and no fallback.

`X-RateLimit-Reset` and `Retry-After` are seconds from now, not timestamps. `Retry-After` is `X-RateLimit-Reset` with a minimum of 1. What "reset" means depends on the algorithm:

| Algorithm | Allowed | Rejected |
|---|---|---|
| Fixed Window | seconds until the current window ends | seconds until the current window ends |
| Sliding Window | seconds until the current window ends | estimated seconds until a request would be allowed |
| Token Bucket | seconds until the bucket is full again | seconds until enough tokens exist for the request |

---

## Testing

```bash
poetry run pytest
```

Tests start their own Redis (version 8) through Testcontainers, so Docker must be running. Nothing else needs to be set up.

```bash
REDIS_IMAGE=redis:5-alpine poetry run pytest     # another Redis version or Valkey
CLUSTER_TESTS=1 poetry run pytest tests/test_cluster.py   # 3-master Redis Cluster
```

The cluster tests are opt-in because they start six Redis processes in one container. They bind ports 17000-17005 (`CLUSTER_BASE_PORT` changes the first one). Without `REQUIRE_CLUSTER=1`, a container that fails to start skips the tests instead of failing them.

Tests cover:
- All three algorithms, including concurrency (50 parallel calls, exact limit enforced), expiry, refill, cost, limit overrides, `peek` and `reset`
- The in-memory limiters, with a fake clock
- Decorator, dependency and middleware behaviour, including custom 429 and 503 handling
- Key functions (IPv6 grouping, forwarded headers, hashing), exemptions, fail-open, fail-closed, the fallback and the circuit breaker
- Redis Cluster
- Public package API

Tests do not wait for real time to pass; they edit the stored state or use a fake clock.

---

## Project structure

```text
src/rate_limiter/
├── __init__.py
├── py.typed
├── clients.py           # RedisClient = Redis | RedisCluster
├── decorators.py        # @rate_limit
├── dependencies.py      # RateLimit dependency
├── exceptions.py        # RateLimitExceeded, RateLimiterUnavailableError
├── keys.py              # default_key_func, ip_key_func, forwarded_key_func, hashed_key_func
├── limits.py            # limit string parser
├── schemas.py           # RateLimitResult
├── algorithms/
│   ├── base.py
│   ├── fixed_window.py
│   ├── sliding_window.py
│   ├── token_bucket.py
│   └── memory.py        # in-memory limiters
├── core/
│   ├── guard.py         # key resolution, cost/limit, exemptions, degraded mode
│   ├── health.py        # circuit breaker, throttled warnings
│   └── response.py      # headers and 429 response
├── lua/
│   ├── fixed_window.lua
│   ├── sliding_window.lua
│   └── token_bucket.lua
└── middleware/
    └── rate_limiter.py  # pure ASGI middleware
```

---

## Development

```bash
poetry install
poetry run pytest
poetry run ruff check . && poetry run ruff format --check .
poetry run mypy .
poetry build
poetry run python benchmarks/bench.py   # benchmarks, starts its own Redis
```

A runnable example is in `examples/demo_app.py`. `docker compose up -d` starts a local Redis for it:

```bash
docker compose up -d
poetry run uvicorn examples.demo_app:app
```

Changes are listed in [CHANGELOG.md](CHANGELOG.md). Releases are created by pushing a `v*` tag on `main`; the release workflow checks the tag against the package version, reruns the checks and publishes a GitHub Release.

---

## License

MIT