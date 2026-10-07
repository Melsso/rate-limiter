# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `allow(key, cost=1, limit=None)`: weighted requests and a per-call limit
  override, for example one limiter shared by several tiers. For `TokenBucket`,
  `limit` replaces the capacity and the refill rate is scaled by the same factor,
  so the time to refill from empty stays the same. A request whose cost exceeds
  the limit is always denied, and a cost below 1 raises `ValueError`.
- `cost` and `limit` arguments on `@rate_limit`, `RateLimit` and
  `RateLimitMiddleware`. Each accepts an `int` or a `Callable[[Request], int]`.
- `peek(key, cost=1, limit=None)` on every limiter: reports whether a request
  would be allowed, and the remaining quota, without consuming anything.
- `reset(key)` on every limiter: forgets all state for a key. The key is the one
  the limiter receives (without `prefix`), so include the namespace yourself.
- `hashed_key_func(key_func, length=32)`: wraps any key function (sync or async)
  and returns a fixed-length SHA-256 digest. Bounds key length and keeps raw
  secrets (such as API keys) out of Redis key names.
- `ip_key_func(ipv6_prefix=64)`: client IP key function with a configurable IPv6
  prefix length, and an `ipv6_prefix` argument on `forwarded_key_func`.
- In-memory limiters `MemoryFixedWindow`, `MemorySlidingWindow` and
  `MemoryTokenBucket`, meant as a `fallback=` for when Redis is down. State is
  per process, so with N workers a client can use N times the limit. At most
  `max_keys` clients are tracked (default 100,000); the least recently used are
  forgotten first.
- `fallback=` argument on `@rate_limit`, `RateLimit` and `RateLimitMiddleware`.
  When Redis raises an error the fallback limiter decides instead, and it takes
  precedence over `fail_open`. Configure it with the same numbers as the
  primary limiter.
- Circuit breaker: after a Redis failure, requests skip Redis for `cooldown`
  seconds (default 5, `0` disables it) and go straight to the fallback or the
  `fail_open` behaviour, instead of waiting for a timeout on every request.
  After the cooldown a single request probes Redis. The breaker is shared by
  every guard that uses the same limiter object.
- `RateLimitExceeded` (429, carries the limiter's `result`) and
  `RateLimiterUnavailableError` (503). Both subclass `HTTPException`, so default
  behaviour is unchanged, and an exception handler can be registered for either
  to customise the response of the decorator and the dependency.
- `on_limit(request, result)` and `on_unavailable(request)` callbacks on
  `RateLimitMiddleware` (sync or async, returning a `Response`). The standard
  `X-RateLimit-*` and `Retry-After` headers are added to an `on_limit` response
  unless it already sets them.
- `from_limit` constructors that take limit strings: `FixedWindow.from_limit(redis,
  "5/minute")`, the same on `SlidingWindow` and `TokenBucket`, and
  `MemoryFixedWindow.from_limit("5/minute")` and friends. Units are `second`,
  `minute`, `hour` and `day` (singular or plural), with an optional multiplier
  such as `"10/5 minutes"`. For `TokenBucket`, `"5/minute"` means capacity 5
  refilled at 5 tokens per 60 seconds.
- `release.yml` workflow: on a `v*` tag it checks the tag against the package
  version and against `main`, runs lint, type checks and tests, builds the
  package, verifies the wheel, and creates a GitHub Release using the matching
  section of this file.
- CI runs the test suite against Redis 5, 6 and 7 and Valkey 8 in addition to
  Redis 8. Locally, set `REDIS_IMAGE` to test against another image.
- Redis Cluster tests (`tests/test_cluster.py`) against a 3-master cluster. They
  run only with `CLUSTER_TESTS=1` and have their own CI job.

### Changed

- **Breaking for custom limiters:** `RateLimiter` subclasses must now implement
  `allow(key, cost, limit)`, `peek(key, cost, limit)` and `reset(key)`.
- `FixedWindow` only increments its counter when a request is allowed. Before,
  denied requests kept incrementing it. Behaviour for cost-1 traffic is the same
  (a blocked client stays blocked until the window ends), but a denied weighted
  request no longer eats quota that smaller requests could still use.
- `default_key_func` and `forwarded_key_func` now group IPv6 clients by `/64`
  network, so one client cannot rotate through addresses of its own prefix to
  dodge a limit. IPv6 keys change shape (for example `2001:db8:1:2::/64`), so
  existing IPv6 counters start fresh after upgrading. IPv4-mapped IPv6 addresses
  are treated as IPv4. Hosts that are not IP addresses are left unchanged.
- `forwarded_key_func` now reads every `X-Forwarded-For` header line, not only
  the first one.
- `@rate_limit` now recognises `Annotated[Request, ...]` and
  `Annotated[Response, ...]` parameters and reuses them.
- The middleware's 503 response is now JSON (`{"detail": "Rate limiter
  unavailable"}`), like the decorator and the dependency. It used to be plain
  text.
- The fail-open warning is throttled once per process (at most every 30
  seconds) instead of once per decorator, dependency or middleware instance. A
  warning is now also logged when requests are rejected because the backend is
  unavailable, and when the fallback is used.
- CI: package build and verification moved from `ci.yml` to `release.yml`.
  `ci.yml` keeps lint, type checks and tests.
- Tests no longer rely on `sleep` to wait for expiry or refill; they edit the
  stored state or use a fake clock instead.

### Fixed

- `@rate_limit` now keeps the `X-RateLimit-*` headers on responses produced when
  the handler raises `HTTPException`. Previously they were dropped.
- `forwarded_key_func(trusted_proxies=0)` now raises `ValueError`. It used to
  silently return the leftmost, client-controlled entry.

## [0.1.0]

Initial release: Fixed Window, Sliding Window and Token Bucket limiters backed by
Redis Lua scripts, with a route decorator, a dependency and a pure ASGI
middleware.