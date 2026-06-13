"""Redis cache wrapper with TTL and invalidation helpers.

Degrades gracefully: if Redis is unreachable, every operation becomes a no-op
(cache miss / silent write) so a Redis outage slows the API down but never
takes it offline — in line with the "degrade where possible" stance in the
architecture doc.
"""
from __future__ import annotations

import json
from typing import Any

try:  # redis is a runtime dep; keep import failures from breaking unit tests
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None  # type: ignore[assignment]


class TTL:
    """Cache lifetimes (seconds) — mirrors the table in architecture-api-first.md."""
    LIBRARY = 15 * 60
    ITEM = 60 * 60
    TMDB = 7 * 24 * 60 * 60
    OMDB = 7 * 24 * 60 * 60
    TMDB_RECS = 24 * 60 * 60
    ARR_QUEUE = 30
    LLM = 24 * 60 * 60


class Cache:
    def __init__(self, url: str | None) -> None:
        self._url = url
        self._client: Any | None = None

    async def connect(self) -> bool:
        if not self._url or aioredis is None:
            self._client = None
            return False
        try:
            client = aioredis.from_url(self._url, decode_responses=True)
            await client.ping()
            self._client = client
            return True
        except Exception:
            self._client = None
            return False

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def get_json(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            raw = await self._client.get(key)
        except Exception:
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        if self._client is None:
            return
        try:
            await self._client.set(key, json.dumps(value), ex=ttl)
        except Exception:
            pass

    async def invalidate(self, *keys: str) -> None:
        if self._client is None or not keys:
            return
        try:
            await self._client.delete(*keys)
        except Exception:
            pass

    async def invalidate_prefix(self, prefix: str) -> None:
        """Drop every key under a prefix (e.g. all of one user's library)."""
        if self._client is None:
            return
        try:
            async for key in self._client.scan_iter(match=f"{prefix}*"):
                await self._client.delete(key)
        except Exception:
            pass

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
