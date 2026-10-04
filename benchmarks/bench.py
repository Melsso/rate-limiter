import asyncio
import platform
import statistics
import sys
import time
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer

from rate_limiter import (
    FixedWindow,
    RateLimit,
    SlidingWindow,
    TokenBucket,
    rate_limit,
)
from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.middleware import RateLimitMiddleware

HUGE = 10**9
Task = Callable[[int], Awaitable[object]]
HEADER = f"{'':<30}{'conc':>6}{'req/s':>12}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}"


async def run_load(
    task: Task, total: int, concurrency: int
) -> tuple[float, list[float]]:
    counter = iter(range(total))
    latencies: list[float] = []

    async def worker() -> None:
        for i in counter:
            start = time.perf_counter()
            await task(i)
            latencies.append(time.perf_counter() - start)

    started = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(concurrency)))
    return time.perf_counter() - started, latencies


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct / 100))]


def print_row(
    label: str, concurrency: int, total: int, elapsed: float, lat: list[float]
) -> None:
    print(
        f"{label:<30}{concurrency:>6}{total / elapsed:>12,.0f}"
        f"{percentile(lat, 50) * 1000:>9.2f}"
        f"{percentile(lat, 95) * 1000:>9.2f}"
        f"{percentile(lat, 99) * 1000:>9.2f}"
    )


def make_limiters(redis: Redis) -> dict[str, RateLimiter]:
    return {
        "fixed_window": FixedWindow(redis, limit=HUGE, window=3600),
        "sliding_window": SlidingWindow(redis, limit=HUGE, window=3600),
        "token_bucket": TokenBucket(redis, capacity=HUGE, refill_rate=1000.0),
    }


def call_allow(limiter: RateLimiter, keys: int) -> Task:
    async def call(i: int) -> object:
        return await limiter.allow(f"k:{i % keys}")

    return call


async def bench_throughput(redis: Redis) -> None:
    print("\n1. allow() throughput and latency")
    print(HEADER)
    for name, limiter in make_limiters(redis).items():
        await redis.flushdb()
        await run_load(call_allow(limiter, 100), 500, 20)
        for concurrency in (1, 10, 50, 200):
            total = 2000 if concurrency == 1 else 10_000
            elapsed, lat = await run_load(call_allow(limiter, 1000), total, concurrency)
            print_row(f"{name} (1000 keys)", concurrency, total, elapsed, lat)
        elapsed, lat = await run_load(call_allow(limiter, 1), 10_000, 50)
        print_row(f"{name} (one hot key)", 50, 10_000, elapsed, lat)


async def bench_exactness(redis: Redis) -> bool:
    print(
        "\n2. Exactness under load (10000 calls, concurrency 200, one key, limit 1000)"
    )
    limit = 1000
    limiters: dict[str, RateLimiter] = {
        "fixed_window": FixedWindow(redis, limit=limit, window=3600),
        "sliding_window": SlidingWindow(redis, limit=limit, window=3600),
        "token_bucket": TokenBucket(redis, capacity=limit, refill_rate=1e-6),
    }
    all_ok = True
    for name, limiter in limiters.items():
        await redis.flushdb()
        outcomes: list[bool] = []

        async def call(
            i: int,
            limiter: RateLimiter = limiter,
            outcomes: list[bool] = outcomes,
        ) -> None:
            outcomes.append((await limiter.allow("hot")).allowed)

        await run_load(call, 10_000, 200)
        allowed = sum(outcomes)
        ok = allowed == limit
        all_ok = all_ok and ok
        print(f"{name:<16} allowed={allowed:<6} {'PASS' if ok else 'FAIL'}")
    return all_ok


def build_apps(redis: Redis) -> dict[str, FastAPI]:
    def client_key(request: Request) -> str:
        return request.headers.get("x-client", "anon")

    def new_limiter(prefix: str) -> FixedWindow:
        return FixedWindow(redis, limit=HUGE, window=3600, prefix=prefix)

    baseline = FastAPI()

    @baseline.get("/")
    async def baseline_root() -> dict[str, bool]:
        return {"ok": True}

    middleware = FastAPI()
    middleware.add_middleware(
        RateLimitMiddleware, limiter=new_limiter("rl:mw"), key_func=client_key
    )

    @middleware.get("/")
    async def middleware_root() -> dict[str, bool]:
        return {"ok": True}

    decorated = FastAPI()

    @decorated.get("/")
    @rate_limit(new_limiter("rl:dec"), key_func=client_key)
    async def decorated_root() -> dict[str, bool]:
        return {"ok": True}

    dependent = FastAPI()
    dependency = RateLimit(new_limiter("rl:dep"), key_func=client_key)

    @dependent.get("/", dependencies=[Depends(dependency)])
    async def dependent_root() -> dict[str, bool]:
        return {"ok": True}

    return {
        "baseline": baseline,
        "middleware": middleware,
        "decorator": decorated,
        "dependency": dependent,
    }


async def drive(
    app: FastAPI, total: int, concurrency: int
) -> tuple[float, list[float]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://bench") as client:

        async def call(i: int) -> object:
            return await client.get("/", headers={"x-client": f"c{i % 1000}"})

        await run_load(call, 200, concurrency)
        return await run_load(call, total, concurrency)


async def bench_integration(redis: Redis) -> None:
    apps = build_apps(redis)
    for concurrency, total in ((1, 2000), (50, 10_000)):
        print(f"\n3. Integration overhead, in-process ASGI, concurrency {concurrency}")
        print(f"{'':<14}{'req/s':>10}{'mean ms':>10}{'p95 ms':>9}{'overhead ms':>13}")
        baseline_mean = 0.0
        for name, app in apps.items():
            await redis.flushdb()
            elapsed, lat = await drive(app, total, concurrency)
            mean = statistics.fmean(lat) * 1000
            if name == "baseline":
                baseline_mean = mean
            print(
                f"{name:<14}{total / elapsed:>10,.0f}{mean:>10.2f}"
                f"{percentile(lat, 95) * 1000:>9.2f}{mean - baseline_mean:>13.2f}"
            )


async def bench_memory(redis: Redis) -> None:
    count = 10_000
    print(f"\n4. Redis memory per tracked client ({count} clients)")
    for name, limiter in make_limiters(redis).items():
        await redis.flushdb()
        before = int((await redis.info("memory"))["used_memory"])
        await run_load(call_allow(limiter, count), count, 50)
        after = int((await redis.info("memory"))["used_memory"])
        print(f"{name:<16} ~{(after - before) / count:,.0f} bytes/client")


async def main() -> int:
    with RedisContainer("redis:8-alpine") as container:
        redis = Redis(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(6379)),
            decode_responses=True,
        )
        try:
            server = (await redis.info("server"))["redis_version"]
            print(f"Python {platform.python_version()} on {platform.platform()}")
            print(f"Redis {server} in Docker, client on the host")
            await bench_throughput(redis)
            exact = await bench_exactness(redis)
            await bench_integration(redis)
            await bench_memory(redis)
        finally:
            await redis.aclose()
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
