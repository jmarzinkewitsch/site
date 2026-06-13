"""M6 content-based recommendation shelves."""
from contextlib import contextmanager

from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from main import create_app
from models import DiscoverItem, LibraryItem

BEARER = "m6-token"
AUTH = {"Authorization": f"Bearer {BEARER}"}


class InMemoryCache:
    def __init__(self): self.store = {}
    async def ping(self): return True
    async def get_json(self, k): return self.store.get(k)
    async def set_json(self, k, v, ttl): self.store[k] = v
    async def invalidate(self, *keys):
        for k in keys: self.store.pop(k, None)
    async def invalidate_prefix(self, p):
        for k in [x for x in self.store if x.startswith(p)]: self.store.pop(k, None)
    async def close(self): pass


class FakeJellyfin:
    def __init__(self):
        self.movies_calls = 0
    async def movies(self, start=0, limit=500):
        self.movies_calls += 1
        return [
            LibraryItem(id="seen", type="Movie", title="Seen Space", genres=["Science Fiction"],
                        played=True, user_rating=9, tmdb_id=1),
            LibraryItem(id="best", type="Movie", title="Recommended Space", genres=["Science Fiction", "Drama"],
                        community_rating=8.4, tmdb_id=2),
            LibraryItem(id="weak", type="Movie", title="Random Comedy", genres=["Comedy"],
                        community_rating=7.0, tmdb_id=3),
        ]
    async def series(self, start=0, limit=500):
        return [
            LibraryItem(id="sseen", type="Series", title="Seen Mystery", genres=["Mystery"],
                        played=True, user_rating=8, tmdb_id=10),
            LibraryItem(id="snew", type="Series", title="New Mystery", genres=["Mystery"],
                        community_rating=8.0, tmdb_id=11),
        ]


class FakeTmdb:
    def __init__(self): self.movie_filters = []
    async def discover_movies(self, page=1, with_genres=None):
        self.movie_filters.append(with_genres)
        return [
            DiscoverItem(tmdb_id=1, type="Movie", title="Already Owned", vote_average=10),
            DiscoverItem(tmdb_id=99, type="Movie", title="Requestable Space", vote_average=8.5),
        ]
    async def discover_series(self, page=1, with_genres=None):
        return [DiscoverItem(tmdb_id=88, type="Series", title="Requestable Mystery", vote_average=8.0)]


@contextmanager
def _client(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.update(
        bearer_token=BEARER,
        jellyfin={"base_url": "http://jf", "api_key": "k", "user_id": "u"},
        tmdb={"api_key": "tk"},
    )
    cache, jf, tmdb = InMemoryCache(), FakeJellyfin(), FakeTmdb()
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_jellyfin] = lambda: jf
    app.dependency_overrides[deps.get_tmdb] = lambda: tmdb
    with TestClient(app) as c:
        c.cache, c.fake_jellyfin, c.fake_tmdb = cache, jf, tmdb
        yield c


def test_library_recommendations_rank_unplayed_matches(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/recommend/library", headers=AUTH)
        assert r.status_code == 200
        items = r.json()
        assert items[0]["item"]["id"] == "best"
        assert items[0]["discover"] is None
        assert "Science Fiction" in items[0]["reason"]
        assert {i["item"]["id"] for i in items} == {"best", "weak"}


def test_discover_recommendations_exclude_owned_and_use_taste_filter(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/recommend/discover", headers=AUTH)
        assert r.status_code == 200
        items = r.json()
        assert [i["discover"]["tmdb_id"] for i in items] == [99]
        assert items[0]["item"] is None
        assert c.fake_tmdb.movie_filters == ["878,9648,18"]


def test_recommendations_are_cached(tmp_path):
    with _client(tmp_path) as c:
        c.get("/recommend/library", headers=AUTH)
        c.get("/recommend/library", headers=AUTH)
        assert c.fake_jellyfin.movies_calls == 1
