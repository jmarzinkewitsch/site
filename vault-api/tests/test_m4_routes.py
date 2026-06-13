"""Route tests for M4: discover, search, request, queue."""
import httpx
import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from main import create_app
from models import DiscoverItem, LibraryItem, RequestResult

BEARER = "m4-token"
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
    async def search(self, term, limit=24):
        return [LibraryItem(id="lib1", type="Movie", title="The Matrix", year=1999, tmdb_id=603)]


class FakeTmdb:
    def __init__(self): self.discover_calls = 0
    async def discover_movies(self, page=1):
        self.discover_calls += 1
        return [DiscoverItem(tmdb_id=603, type="Movie", title="The Matrix")]
    async def discover_series(self, page=1):
        return [DiscoverItem(tmdb_id=1396, type="Series", title="Breaking Bad")]
    async def series_tvdb_id(self, tmdb_id):
        return 81189 if tmdb_id == 1396 else None


class FakeRadarr:
    def __init__(self): self.added = []
    async def add(self, tmdb_id, *a, **k):
        self.added.append(tmdb_id)
        return RequestResult(ok=True, status="added", title="The Matrix", arr_id=7)


class FakeSonarr:
    def __init__(self): self.added = []
    async def add(self, tvdb_id, *a, **k):
        self.added.append(tvdb_id)
        return RequestResult(ok=True, status="added", title="Breaking Bad", arr_id=3)


def _mock_http() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/3/search/movie":
            return httpx.Response(200, json={"results": [
                {"id": 603, "title": "The Matrix"},   # already owned → dedup
                {"id": 604, "title": "Matrix Resurrections"},
            ]})
        if path == "/3/search/tv":
            return httpx.Response(200, json={"results": [{"id": 1396, "name": "Breaking Bad"}]})
        if path == "/api/v3/queue":
            host = request.url.host
            title = "Movie DL" if host == "radarr" else "Series DL"
            return httpx.Response(200, json={"records": [
                {"title": title, "size": 100, "sizeleft": 50, "status": "downloading"}]})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def m4(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.update(
        bearer_token=BEARER,
        jellyfin={"base_url": "http://jf", "api_key": "k", "user_id": "u"},
        tmdb={"api_key": "tk"},
        radarr={"base_url": "http://radarr", "api_key": "rk"},
        sonarr={"base_url": "http://sonarr", "api_key": "sk"},
    )
    fake_tmdb, fake_radarr, fake_sonarr = FakeTmdb(), FakeRadarr(), FakeSonarr()
    cache = InMemoryCache()
    http = _mock_http()

    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_http] = lambda: http
    app.dependency_overrides[deps.get_jellyfin] = lambda: FakeJellyfin()
    app.dependency_overrides[deps.get_tmdb] = lambda: fake_tmdb
    app.dependency_overrides[deps.get_radarr] = lambda: fake_radarr
    app.dependency_overrides[deps.get_sonarr] = lambda: fake_sonarr

    with TestClient(app) as c:
        c.fake_tmdb, c.fake_radarr, c.fake_sonarr, c.cache = fake_tmdb, fake_radarr, fake_sonarr, cache
        yield c


def test_discover_requires_bearer(m4):
    assert m4.get("/discover/movies").status_code == 401


def test_discover_movies_cached(m4):
    assert m4.get("/discover/movies", headers=AUTH).json()[0]["title"] == "The Matrix"
    m4.get("/discover/movies", headers=AUTH)  # served from cache
    assert m4.fake_tmdb.discover_calls == 1


def test_search_tags_playable_and_requestable(m4):
    r = m4.get("/search", params={"q": "matrix"}, headers=AUTH)
    assert r.status_code == 200
    items = r.json()
    playable = [i for i in items if i["status"] == "playable"]
    requestable = [i for i in items if i["status"] == "requestable"]
    assert [i["library_id"] for i in playable] == ["lib1"]
    # 603 is owned → must not reappear as requestable; 604 + series 1396 do.
    assert 603 not in [i["tmdb_id"] for i in requestable]
    assert {604, 1396} == {i["tmdb_id"] for i in requestable}


def test_request_movie(m4):
    m4.cache.store["request:queue"] = [{"stale": True}]
    r = m4.post("/request/movie", headers=AUTH, json={"tmdb_id": 603})
    assert r.status_code == 200
    assert r.json()["status"] == "added"
    assert m4.fake_radarr.added == [603]
    assert "request:queue" not in m4.cache.store  # invalidated


def test_request_series_resolves_tvdb(m4):
    r = m4.post("/request/series", headers=AUTH, json={"tmdb_id": 1396})
    assert r.status_code == 200
    assert m4.fake_sonarr.added == [81189]  # tmdb 1396 → tvdb 81189


def test_request_series_without_tvdb_is_422(m4):
    r = m4.post("/request/series", headers=AUTH, json={"tmdb_id": 999})
    assert r.status_code == 422


def test_queue_combines_radarr_and_sonarr(m4):
    r = m4.get("/request/queue", headers=AUTH)
    assert r.status_code == 200
    items = r.json()
    titles = {i["title"] for i in items}
    assert titles == {"Movie DL", "Series DL"}
    assert all(i["progress"] == 0.5 for i in items)
