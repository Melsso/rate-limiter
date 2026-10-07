import math
import threading
import time
from abc import abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Self

from rate_limiter.algorithms.base import RateLimiter, check_cost, check_limit
from rate_limiter.limits import parse_limit
from rate_limiter.schemas import RateLimitResult

DEFAULT_MAX_KEYS = 100_000

Clock = Callable[[], float]


class _MemoryLimiter(RateLimiter):
    def __init__(self, max_keys: int, clock: Clock) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be >= 1")
        self.max_keys = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        self._state: OrderedDict[str, Any] = OrderedDict()

    def __len__(self) -> int:
        with self._lock:
            return len(self._state)

    def _load(self, key: str) -> Any:
        value = self._state.get(key)
        if value is not None:
            self._state.move_to_end(key)
        return value

    def _save(self, key: str, value: Any) -> None:
        self._state[key] = value
        self._state.move_to_end(key)
        while len(self._state) > self.max_keys:
            self._state.popitem(last=False)

    @abstractmethod
    def _evaluate(
        self, key: str, cost: int, limit: int | None, consume: bool
    ) -> RateLimitResult: ...

    async def allow(
        self, key: str, cost: int = 1, limit: int | None = None
    ) -> RateLimitResult:
        return self._evaluate(key, cost, limit, consume=True)

    async def peek(
        self, key: str, cost: int = 1, limit: int | None = None
    ) -> RateLimitResult:
        return self._evaluate(key, cost, limit, consume=False)

    async def reset(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)


class MemoryFixedWindow(_MemoryLimiter):
    def __init__(
        self,
        limit: int,
        window: int,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Clock = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window < 1:
            raise ValueError("window must be >= 1")
        super().__init__(max_keys, clock)
        self.limit = limit
        self.window = window

    @classmethod
    def from_limit(
        cls,
        spec: str,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Clock = time.monotonic,
    ) -> Self:
        limit, window = parse_limit(spec)
        return cls(limit, window, max_keys=max_keys, clock=clock)

    def _evaluate(
        self, key: str, cost: int, limit: int | None, consume: bool
    ) -> RateLimitResult:
        check_cost(cost)
        if limit is not None:
            check_limit(limit)
        effective = self.limit if limit is None else limit

        with self._lock:
            now = self._clock()
            entry = self._load(key)
            if entry is not None and entry[1] <= now:
                self._state.pop(key, None)
                entry = None

            count, expires = entry if entry is not None else (0, 0.0)
            allowed = count + cost <= effective
            if allowed and consume:
                if entry is None:
                    count, expires = cost, now + self.window
                else:
                    count += cost
                self._save(key, (count, expires))

            ttl = max(0, math.ceil(expires - now)) if count > 0 else 0

        return RateLimitResult(
            allowed=allowed,
            limit=effective,
            remaining=max(0, effective - count),
            reset_after=ttl,
        )


class MemorySlidingWindow(_MemoryLimiter):
    def __init__(
        self,
        limit: int,
        window: int,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Clock = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window < 1:
            raise ValueError("window must be >= 1")
        super().__init__(max_keys, clock)
        self.limit = limit
        self.window = window

    @classmethod
    def from_limit(
        cls,
        spec: str,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Clock = time.monotonic,
    ) -> Self:
        limit, window = parse_limit(spec)
        return cls(limit, window, max_keys=max_keys, clock=clock)

    def _evaluate(
        self, key: str, cost: int, limit: int | None, consume: bool
    ) -> RateLimitResult:
        check_cost(cost)
        if limit is not None:
            check_limit(limit)
        effective = self.limit if limit is None else limit
        window = self.window

        with self._lock:
            now = self._clock()
            idx = math.floor(now / window)
            elapsed = now - idx * window

            state = self._load(key)
            if state is None or idx > state[0] + 1:
                w, c, p = idx, 0, 0
            elif idx == state[0] + 1:
                w, c, p = idx, 0, state[1]
            else:
                w, c, p = state

            weight = (window - elapsed) / window
            estimated = p * weight + c

            allowed = estimated + cost <= effective
            if allowed and consume:
                c += cost
                estimated += cost
            if consume:
                self._save(key, (w, c, p))

        retry: float = math.ceil(window - elapsed)
        if not allowed:
            if cost > effective:
                retry = window
            else:
                room = effective - c - cost
                if room >= 0 and p > 0:
                    retry = (window - room * window / p) - elapsed
                elif c > 0:
                    retry = (window - elapsed) + window * (1 - (effective - cost) / c)
                retry = math.ceil(retry)
        retry = max(1, int(retry))

        return RateLimitResult(
            allowed=allowed,
            limit=effective,
            remaining=max(0, math.floor(effective - estimated)),
            reset_after=retry,
        )


class MemoryTokenBucket(_MemoryLimiter):
    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Clock = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be > 0")
        super().__init__(max_keys, clock)
        self.capacity = capacity
        self.refill_rate = refill_rate

    @classmethod
    def from_limit(
        cls,
        spec: str,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Clock = time.monotonic,
    ) -> Self:
        capacity, seconds = parse_limit(spec)
        return cls(capacity, capacity / seconds, max_keys=max_keys, clock=clock)

    def _evaluate(
        self, key: str, cost: int, limit: int | None, consume: bool
    ) -> RateLimitResult:
        check_cost(cost)
        if limit is None:
            capacity = self.capacity
            rate = self.refill_rate
        else:
            check_limit(limit)
            capacity = limit
            rate = self.refill_rate * limit / self.capacity

        with self._lock:
            now = self._clock()
            state = self._load(key)
            tokens, ts = state if state is not None else (float(capacity), now)

            tokens = min(capacity, tokens + max(0.0, now - ts) * rate)

            allowed = tokens >= cost
            if allowed and consume:
                tokens -= cost
            if consume:
                self._save(key, (tokens, now))

        if allowed:
            reset = math.ceil((capacity - tokens) / rate)
        else:
            reset = math.ceil((cost - tokens) / rate)

        return RateLimitResult(
            allowed=allowed,
            limit=capacity,
            remaining=math.floor(tokens),
            reset_after=reset,
        )
