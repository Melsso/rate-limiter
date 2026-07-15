# Rate Limiter

A Redis-backed async rate limiter library for FastAPI applications.

Supports multiple rate limiting algorithms:
- Fixed Window
- Sliding Window
- Token Bucket

Built with:
- Python 3.11+
- FastAPI
- Redis
- Lua scripts for atomic operations
- Poetry

---

## Features

- Async-first implementation
- Redis-backed storage
- Atomic Redis operations using Lua
- Multiple rate limiting algorithms
- FastAPI middleware support
- FastAPI route decorator support
- Configurable limits and windows
- Fully tested with real Redis containers

---

## Architecture

```text
             FastAPI Application
                     |
          +----------+----------+
          |                     |
      Middleware             Decorator
          |                     |
          +----------+----------+
                     |
              RateLimiter API
                     |
    +----------------+----------------+
    |                |                |
Fixed Window Sliding Window Token Bucket
    |                |                |
    +----------------+----------------+
                     |
                   Redis
                (Lua scripts)
```

---

## Installation

Clone the repository:
```bash
    git clone https://github.com/<username>/rate-limiter.git
    cd rate-limiter
```

Install dependencies:
```bash
    poetry install
```

---

## Running Redis:

Start Redis locally:
```bash
    docker compose up -d
```

The project expects:
```text
    redis://localhost:6379
```

You can override this using environment variables.

Create:
```bash
    .env
```

Example:
```bash
    REDIS_URL=redis://localhost:6379
    RATE_LIMIT=5
    RATE_WINDOW=60
```

---

## Usage

### Fixed Window
```python
    from redis.asyncio import Redis
    from rate_limiter import FixedWindow

    redis = Redis.from_url(
        "redis://localhost:6379"
    )

    limiter = FixedWindow(
        redis=redis,
        limit=100,
        window=60,
    )
```

### FastAPI Middleware

Apply rate limiting globally:
```python
    from fastapi import FastAPI
    from rate_limiter import FixedWindow
    from rate_limiter.middleware import RateLimitMiddleware

    app = FastAPI()

    limiter = FixedWindow(
        redis=redis,
        limit=100,
        window=60,
    )

    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
    )


    @app.get("/")
    async def root():
        return {
            "message": "hello"
        }
```
Every request is now rate limited.

### Route Decorator

Apply rate limiting only to specific endpoints:
```python
    from fastapi import Request
    from rate_limiter import rate_limit

    @app.get("/login")
    @rate_limit(limiter)
    async def login(request: Request):
        return {
            "message": "logged in"
        }
```

---

## Algorithms

### Fixed Window

Counts requests inside fixed time intervals.
Example:
```text
    12:00:00 - 12:01:00
    limit: 100 requests
```
Pros:
- Simple
- Fast

Cons:
- Boundary bursts possible

### Sliding Window

Uses the previous and current windows to calculate a weighted request count.
Pros:
- Smoother limiting
- Avoids fixed window boundary spikes

Cons:
- More Redis operations

### Token Bucket

Maintains a bucket of tokens that refill over time.
Pros:
- Allows controlled bursts
- Common in production systems

Cons:
- More complex state management

---

## Redis Atomicity

All state-changing algorithms use Redis Lua scripts.
Example flow:

```text
Request
   |
   v
Redis Lua Script
   |
   +-- increment/check state
   |
   +-- calculate remaining quota
   |
   +-- update expiration
   |
   v
Response
```
This guarantees atomic operations even with concurrent requests.

---

## Testing

Run the test suite:
```bash
    poetry run pytest
```

Tests cover:
- Rate limiting algorithms
- Redis Lua execution
- Middleware behavior
- Decorator behavior
- Public package API

Tests use real Redis containers through Testcontainers.

---

## Project Structure
```text
src/rate_limiter/

├── algorithms/
│   ├── base.py
│   ├── fixed_window.py
│   ├── sliding_window.py
│   └── token_bucket.py
│
├── middleware/
│   └── rate_limiter.py
│
├── core/
│   ├── container.py
│   ├── redis.py
│   ├── config.py
│   └── response.py
│
├── main.py
│
├── schemas.py
├── decorators.py
└── __init__.py
```

---

## Development

Install:
```bash
    poetry install
```

Start Redis:
```bash
    docker compose up -d
```

Run tests:
```bash
    poetry run pytest
```

Build package:
```bash
    poetry build
```

---

## Roadmap

- [x] Fixed Window limiter
- [x] Sliding Window limiter
- [x] Token Bucket limiter
- [x] Redis Lua atomic operations
- [x] FastAPI middleware
- [x] Route decorator
- [x] Test coverage
- [ ] API key based rate limiting
- [ ] User identity strategies
- [ ] Distributed benchmarks
- [ ] Publish package to PyPI

---

## License
MIT License
