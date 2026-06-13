"""Item-detail enrichment with OMDb scores (M5)."""
import httpx
import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from main import create_app
from models import LibraryItem

BEARER = "m5-token"
AUTH = {"Authorization": f"Bearer {BEARER}"}

OMDB_SAMPLE = {
    "Response": "True", "imdbRating": "8.7",
    "Ratings": [{"Source": "Rotten Tomatoes", "Value": "88%"}],
}


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
    def __init__(self): self.item_calls = 0
    async def item(self, item_id):
        self.item_calls += 1
        return LibraryItem(id=item_id, type="Movie", title="The Matrix",
                           community_rating=8.2, imdb_id="tt0133093")


def _omdb_http() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("i") == "tt0133093":
            return httpx.Response(200, json=OMDB_SAMPLE)
        return httpx.Response(200, json={"Response": "False"})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _client(tmp_path, omdb_configured: bool, cache, fake_jf, http):
    store = ConfigStore(tmp_path / "config.json")
    sections = {
        "bearer_token": BEARER,
        "jellyfin": {"base_url": "http://jf", "api_key": "k", "user_id": "u"},
    }
    if omdb_configured:
        sections["omdb"] = {"api_key": "ok"}
    store.update(**sections)
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_http] = lambda: http
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jf
    return TestClient(app)


def test_item_detail_includes_omdb_scores(tmp_path):
    cache, fake_jf, http = InMemoryCache(), FakeJellyfin(), _omdb_http()
    with _client(tmp_path, True, cache, fake_jf, http) as c:
        r = c.get("/library/item/m1", headers=AUTH)
        assert r.status_code == 200
        scores = r.json()["external_scores"]
        assert scores["imdb"] == 8.7
        assert scores["rotten_tomatoes"] == 88
        # Scores are cached separately by IMDB id (7d TTL).
        assert "omdb:tt0133093" in cache.store


def test_item_detail_without_omdb_has_no_scores(tmp_path):
    cache, fake_jf, http = InMemoryCache(), FakeJellyfin(), _omdb_http()
    with _client(tmp_path, False, cache, fake_jf, http) as c:
        r = c.get("/library/item/m1", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["external_scores"] is None
        assert "omdb:tt0133093" not in cache.store
