import asyncio

from rate_limiter import TokenBucket


def test_token_bucket_benchmark(benchmark, benchmark_redis):
    limiter = TokenBucket(
        redis=benchmark_redis,
        capacity=100000,
        refill_rate=1000,
    )

    async def request():
        await limiter.allow("user")

    loop = asyncio.new_event_loop()

    def run():
        loop.run_until_complete(request())

    benchmark(run)

    loop.run_until_complete(benchmark_redis.aclose())
    loop.close()



def test_token_bucket_concurrent_benchmark(
    benchmark,
    benchmark_redis,
    benchmark_loop,
):
    limiter = TokenBucket(
    redis=benchmark_redis,
        capacity=100000,
        refill_rate=1000,
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