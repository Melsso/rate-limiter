from abc import ABC, abstractmethod


class Storage(ABC):

    @abstractmethod
    async def increment(self, key: str) -> int:
        ...

    @abstractmethod
    async def get(self, key: str):
        ...

    @abstractmethod
    async def expire(self, key: str, seconds: int):
        ...

    @abstractmethod
    async def delete(self, key: str):
        ...