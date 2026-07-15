import asyncio

from rate_limiter import FixedWindow


def test_fixed_window_benchmark(benchmark, benchmark_redis):
    limiter = FixedWindow(
        redis=benchmark_redis,
        limit=100000,
        window=60,
    )

    async def request():
        await limiter.allow("user")

    loop = asyncio.new_event_loop()

    def run():
        loop.run_until_complete(request())

    benchmark(run)

    loop.run_until_complete(benchmark_redis.aclose())
    loop.close()


def test_fixed_window_concurrent_benchmark(
    benchmark,
    benchmark_redis,
    benchmark_loop,
):
    limiter = FixedWindow(
        redis=benchmark_redis,
        limit=100000,
        window=60,
    )

    async def worker():
        await limiter.allow("user")

    async def run():
        await asyncio.gather(
            *(worker() for _ in range(100))
        )

    def bench():
        benchmark_loop.run_until_complete(run())

    benchmark(bench)