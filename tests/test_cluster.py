import asyncio
import os
import time

import pytest
import pytest_asyncio
from redis.asyncio.cluster import RedisCluster
from testcontainers.core.container import DockerContainer

from rate_limiter import FixedWindow, SlidingWindow, TokenBucket

pytestmark = pytest.mark.skipif(
    os.environ.get("CLUSTER_TESTS") != "1",
    reason="set CLUSTER_TESTS=1 to run the Redis Cluster tests",
)

CLUSTER_IMAGE = os.environ.get("CLUSTER_IMAGE", "grokzen/redis-cluster:7.0.10")
BASE_PORT = int(os.environ.get("CLUSTER_BASE_PORT", "17000"))
PORTS = range(BASE_PORT, BASE_PORT + 6)

MAX_IN_FLIGHT = 50


async def gather_bounded(func, items):
    semaphore = asyncio.Semaphore(MAX_IN_FLIGHT)

    async def run(item):
        async with semaphore:
            return await func(item)

    return await asyncio.gather(*(run(item) for item in items))


@pytest.fixture(scope="session")
def cluster_container():
    container = (
        DockerContainer(CLUSTER_IMAGE)
        .with_env("IP", "127.0.0.1")
        .with_env("INITIAL_PORT", str(BASE_PORT))
    )
    for port in PORTS:
        container.with_bind_ports(port, port)
    try:
        container.start()
    except Exception as exc:
        if os.environ.get("REQUIRE_CLUSTER") == "1":
            raise
        pytest.skip(f"cannot start the cluster container: {exc!r}")
    try:
        yield container
    finally:
        container.stop()


@pytest_asyncio.fixture
async def cluster(cluster_container):
    deadline = time.monotonic() + 120
    while True:
        client = RedisCluster(host="127.0.0.1", port=BASE_PORT, decode_responses=True)
        try:
            await client.initialize()
            await client.set("rl:ready", "1")
            break
        except Exception:
            await client.aclose()
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(1)
    yield client
    await client.flushall(target_nodes=RedisCluster.PRIMARIES)
    await client.aclose()


@pytest.fixture(params=["fixed_window", "sliding_window", "token_bucket"])
def limiter(request, cluster):
    if request.param == "fixed_window":
        return FixedWindow(cluster, limit=10, window=3600)
    if request.param == "sliding_window":
        return SlidingWindow(cluster, limit=10, window=3600)
    return TokenBucket(cluster, capacity=10, refill_rate=1e-6)


@pytest.mark.asyncio
async def test_exact_limit_under_concurrency(limiter):
    results = await asyncio.gather(*(limiter.allow("u") for _ in range(50)))

    assert sum(r.allowed for r in results) == 10


@pytest.mark.asyncio
async def test_keys_on_every_node_work(limiter, cluster):
    keys = [f"user:{i}" for i in range(300)]
    nodes = {cluster.get_node_from_key(f"{limiter.prefix}:{k}").name for k in keys}
    assert len(nodes) == 3

    results = await gather_bounded(limiter.allow, keys)

    assert all(r.allowed for r in results)
    assert all(r.remaining == 9 for r in results)


@pytest.mark.asyncio
async def test_cost_limit_peek_and_reset(limiter):
    assert (await limiter.allow("u", cost=4)).remaining == 6
    assert (await limiter.peek("u")).remaining == 6
    assert (await limiter.allow("u", limit=4)).limit == 4

    await limiter.reset("u")

    assert (await limiter.peek("u")).remaining == 10


@pytest.mark.asyncio
async def test_recovers_after_scripts_are_flushed(limiter, cluster):
    keys = [f"user:{i}" for i in range(100)]
    await gather_bounded(limiter.allow, keys)

    await cluster.execute_command(
        "SCRIPT", "FLUSH", target_nodes=RedisCluster.PRIMARIES
    )

    results = await gather_bounded(limiter.allow, keys)
    assert all(r.allowed for r in results)
