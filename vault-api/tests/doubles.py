"""Shared test doubles used across the route/service tests."""
from __future__ import annotations

from typing import Any


class InMemoryCache:
    """Cache double with the same surface as cache.Cache."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def ping(self) -> bool:
        return True

    async def get_json(self, key: str):
        return self.store.get(key)

    async def set_json(self, key: str, value, ttl: int) -> None:
        self.store[key] = value

    async def invalidate(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)

    async def invalidate_prefix(self, prefix: str) -> None:
        for key in [k for k in self.store if k.startswith(prefix)]:
            self.store.pop(key, None)

    async def close(self) -> None:
        pass
