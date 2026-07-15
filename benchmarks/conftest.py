import asyncio
import pytest
import redis.asyncio as redis


@pytest.fixture
def benchmark_redis():
    return redis.Redis(
        host="localhost",
        port=6379,
        decode_responses=True,
    )


@pytest.fixture
def benchmark_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()