"""Test fixtures: an in-memory cache, a fake Jellyfin, and a wired TestClient."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore, JellyfinConfig, VaultConfig
from main import create_app
from models import LibraryItem, StreamInfo


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


class FakeJellyfin:
    """Records calls so tests can assert caching/invalidation behaviour."""

    def __init__(self) -> None:
        self.movies_calls = 0
        self.progress_calls: list[tuple] = []
        self.item_error: Exception | None = None
        self._item = LibraryItem(id="m1", type="Movie", title="Blade Runner", year=1982)

    async def movies(self, start: int = 0, limit: int = 100):
        self.movies_calls += 1
        return [self._item]

    async def series(self, start: int = 0, limit: int = 100):
        return [LibraryItem(id="s1", type="Series", title="Severance")]

    async def continue_watching(self, limit: int = 12):
        return [self._item]

    async def item(self, item_id: str):
        if self.item_error:
            raise self.item_error
        return self._item

    async def report_progress(self, item_id, position_seconds, is_paused):
        self.progress_calls.append((item_id, position_seconds, is_paused))

    def stream(self, item_id, media_source_id=None):
        return StreamInfo(url=f"http://jellyfin.local/Videos/{item_id}/stream?static=true&api_key=k")


BEARER = "test-bearer-token"


@pytest.fixture
def store(tmp_path) -> ConfigStore:
    s = ConfigStore(tmp_path / "config.json")
    s.update(
        bearer_token=BEARER,
        jellyfin={"base_url": "http://jf.local", "api_key": "k", "user_id": "u1"},
    )
    return s


@pytest.fixture
def fake_jellyfin() -> FakeJellyfin:
    return FakeJellyfin()


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache()


@pytest.fixture
def client(store, fake_jellyfin, cache):
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jellyfin
    with TestClient(app) as c:
        c.fake_jellyfin = fake_jellyfin
        c.cache = cache
        yield c


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {BEARER}"}
