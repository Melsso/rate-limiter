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
- `X-RateLimit-*` headers on every response, `Retry-After` on rejections
- Custom client identification (`key_func`, sync or async), with a safe `X-Forwarded-For` helper
- Fail-open or fail-closed behaviour when Redis is unavailable
- Per-limiter key prefixes and per-route namespaces
- One Redis key per client and limiter (designed to be cluster-friendly, not yet tested against a cluster)
- Typed (`py.typed`)
- Tested against real Redis containers

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
     (key_func, exemptions, fail-open/closed)
                     |
              RateLimiter API
                     |
    +----------------+----------------+
    |                |                |
Fixed Window   Sliding Window    Token Bucket
    |                |                |
    +----------------+----------------+
                     |
                   Redis
                (Lua scripts)
```

---

## Installation

Requires Python 3.11+ and Redis 5+.

```bash
pip install git+https://github.com/Melsso/rate-limiter.git@v0.1.0
```

or with Poetry:

```bash
poetry add git+https://github.com/Melsso/rate-limiter.git@v0.1.0
```

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

Every response carries:

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
- Handlers do not need to declare `request` or `response`; they are injected for you. If your handler already declares them, they are reused.
- Works with `async def` and plain `def` handlers.
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

---

## Options

| Option | Decorator | Dependency | Middleware | Default | Meaning |
|---|---|---|---|---|---|
| `key_func` | yes | yes | yes | client IP | Picks who is limited. Receives the `Request`, returns a `str` (sync or async) |
| `fail_open` | yes | yes | yes | `True` | If Redis fails, let the request through. With `False`, respond `503` |
| `exempt_when` | yes | yes | yes | `None` | `Callable[[Request], bool]`; matching requests are not counted |
| `namespace` | yes | yes | no | `None` | Separates counters of routes that share one limiter |
| `exclude_paths` | no | no | yes | `()` | Exact paths that skip limiting |
| `exclude_methods` | no | no | yes | `("OPTIONS",)` | HTTP methods that skip limiting |

Each limiter also takes a `prefix` (`rl:fw`, `rl:sw` and `rl:tb` by default). Keys are stored as `<prefix>:<key>`. Give each limiter its own prefix, or use `namespace`, otherwise routes sharing a limiter share counters.

```python
@app.get("/a")
@rate_limit(limiter, namespace="a")
async def a(): ...


@app.get("/b")
@rate_limit(limiter, namespace="b")
async def b(): ...
```

### Identifying clients

The default key is the socket's client IP. This has two consequences:

- Behind a reverse proxy, that IP is the proxy's, so all users share one limit.
- Behind a unix socket, `request.client` is `None` and everyone shares the key `"unknown"`.

If you run uvicorn behind a proxy, use `--proxy-headers --forwarded-allow-ips=<proxy ip>`, or use the helper:

```python
from rate_limiter import forwarded_key_func


@app.get("/")
@rate_limit(limiter, key_func=forwarded_key_func(trusted_proxies=1))
async def root(): ...
```

`forwarded_key_func` counts hops from the right of `X-Forwarded-For`, so entries a client adds on its own are ignored. It is only safe when your proxy appends the real peer address (Nginx: `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`).

Limiting by API key or user:

```python
async def by_user(request):
    return request.headers.get("x-api-key") or request.client.host
```

### When Redis is down

With `fail_open=True` (default) requests pass through and a warning is logged to the `rate_limiter` logger at most once every 30 seconds. With `fail_open=False`, requests get `503`.

Fail-open only helps when Redis raises an error. Redis-py waits forever by default, so create your client with `socket_timeout` and `socket_connect_timeout` (as in the quick start).

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

A bucket of up to `capacity` tokens that refills at `refill_rate` tokens per second. Each request takes one token. `5 / 60` means five tokens per minute.

Pros:
- Allows controlled bursts
- Common in production systems

Cons:
- More state to reason about

Invalid arguments (`limit`, `window`, `capacity` below 1, or `refill_rate` of 0 or less) raise `ValueError`.

---

## Redis atomicity

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
- Each script touches a single Redis key per client and limiter, which avoids multi-key slot problems in Redis Cluster (not yet tested against a cluster).
- Keys expire on their own; nothing needs cleaning up.

---

## Response format

| Situation | Status | Headers | Body |
|---|---|---|---|
| Allowed | handler's | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` | handler's |
| Rejected | 429 | the three above + `Retry-After` | `{"detail": "Too Many Requests"}` |
| Redis down, `fail_open=False` | 503 | none | `Rate limiter unavailable` |

`X-RateLimit-Reset` and `Retry-After` are seconds from now, not timestamps.

---

## Testing

```bash
poetry run pytest
```

Tests start their own Redis through Testcontainers, so Docker must be running. Nothing else needs to be set up.

Tests cover:
- All three algorithms, including concurrency (50 parallel calls, exact limit enforced), expiry and refill
- Decorator, dependency and middleware behaviour
- Key functions, exemptions, fail-open and fail-closed
- Public package API

---

## Project structure

```text
src/rate_limiter/
├── __init__.py
├── py.typed
├── decorators.py        # @rate_limit
├── dependencies.py      # RateLimit dependency
├── keys.py              # default_key_func, forwarded_key_func
├── schemas.py           # RateLimitResult
├── algorithms/
│   ├── base.py
│   ├── fixed_window.py
│   ├── sliding_window.py
│   └── token_bucket.py
├── core/
│   ├── guard.py         # key resolution, exemptions, fail-open
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

---

## Roadmap

- [x] Fixed Window limiter
- [x] Sliding Window limiter
- [x] Token Bucket limiter
- [x] Redis Lua atomic operations
- [x] FastAPI middleware
- [x] Route decorator and dependency
- [x] Custom client identification (`key_func`)
- [x] Fail-open / fail-closed
- [x] Test coverage
- [ ] Limit strings such as `"5/minute"`
- [ ] Weighted request costs
- [ ] Custom 429 handlers
- [ ] Distributed benchmarks
- [ ] Publish package to PyPI

---

## License

MIT