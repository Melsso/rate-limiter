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
- `release.yml` workflow: on a `v*` tag it checks the tag against the package
  version and against `main`, runs lint, type checks and tests, builds the
  package, verifies the wheel, and creates a GitHub Release using the matching
  section of this file.

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
- CI: package build and verification moved from `ci.yml` to `release.yml`.
  `ci.yml` keeps lint, type checks and tests.

### Fixed

- `@rate_limit` now keeps the `X-RateLimit-*` headers on responses produced when
  the handler raises `HTTPException`. Previously they were dropped.
- `forwarded_key_func(trusted_proxies=0)` now raises `ValueError`. It used to
  silently return the leftmost, client-controlled entry.

## [0.1.0]

Initial release: Fixed Window, Sliding Window and Token Bucket limiters backed by
Redis Lua scripts, with a route decorator, a dependency and a pure ASGI
middleware.