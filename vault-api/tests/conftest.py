"""Test fixtures: an in-memory cache, a fake Jellyfin, and a wired TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from doubles import InMemoryCache
from main import create_app
from models import LibraryItem, StreamInfo


class FakeJellyfin:
    """Records calls so tests can assert caching/invalidation behaviour."""

    def __init__(self) -> None:
        self.movies_calls = 0
        self.latest_calls = 0
        self.seasons_calls = 0
        self.episodes_calls = 0
        self.progress_calls: list[tuple] = []
        self.ratings: list[tuple] = []
        self.item_error: Exception | None = None
        self.movies_error: Exception | None = None
        self.progress_error: Exception | None = None
        self._item = LibraryItem(id="m1", type="Movie", title="Blade Runner", year=1982)

    async def movies(self, start: int = 0, limit: int = 100):
        if self.movies_error:
            raise self.movies_error
        self.movies_calls += 1
        return [self._item]

    async def series(self, start: int = 0, limit: int = 100):
        return [LibraryItem(id="s1", type="Series", title="Severance")]

    async def latest(self, include_type: str, limit: int = 16):
        self.latest_calls += 1
        return [LibraryItem(id="new1", type=include_type, title="Freshly Added")]

    async def seasons(self, series_id: str):
        self.seasons_calls += 1
        return [LibraryItem(id="season1", type="Season", title="Season 1", series_id=series_id, index_number=1)]

    async def episodes(self, series_id: str, season_id: str):
        self.episodes_calls += 1
        return [LibraryItem(
            id="e1", type="Episode", title="Good News About Hell",
            series_id=series_id, season_id=season_id, series_name="Severance",
            parent_index_number=1, index_number=1, episode_code="S1 E1",
            runtime_seconds=3420,
        )]

    async def continue_watching(self, limit: int = 12):
        return [self._item]

    async def search(self, term: str, limit: int = 24):
        return [self._item]

    async def item(self, item_id: str):
        if self.item_error:
            raise self.item_error
        return self._item

    async def report_progress(self, item_id, position_seconds, is_paused):
        if self.progress_error:
            raise self.progress_error
        self.progress_calls.append((item_id, position_seconds, is_paused))

    async def set_rating(self, item_id, rating):
        self.ratings.append((item_id, rating))

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
