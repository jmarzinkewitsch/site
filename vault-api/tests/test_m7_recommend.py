"""M7 recommendation route: algorithmic shelves with optional Claude polish."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from main import create_app
from models import DiscoverItem, LibraryItem

BEARER = "m7-token"
AUTH = {"Authorization": f"Bearer {BEARER}"}


class InMemoryCache:
    def __init__(self): self.store = {}
    async def ping(self): return True
    async def get_json(self, k): return self.store.get(k)
    async def set_json(self, k, v, ttl): self.store[k] = v
    async def invalidate(self, *keys):
        for k in keys: self.store.pop(k, None)
    async def invalidate_prefix(self, p): pass
    async def close(self): pass


class FakeJellyfin:
    def __init__(self): self.movies_calls = 0
    async def movies(self, start=0, limit=100):
        self.movies_calls += 1
        return [LibraryItem(
            id="m1", type="Movie", title="Blade Runner", year=1982,
            genres=["Sci-Fi"], user_rating=9, community_rating=8.1,
            tmdb_id=78, played=True,
        )]
    async def series(self, start=0, limit=100):
        return [LibraryItem(id="s1", type="Series", title="Severance", genres=["Sci-Fi"], user_rating=8)]
    async def latest(self, include_type, limit=30):
        return []


class FakeTmdb:
    async def discover_movies(self, page=1):
        return [
            DiscoverItem(tmdb_id=78, type="Movie", title="Blade Runner"),
            DiscoverItem(tmdb_id=603, type="Movie", title="The Matrix", vote_average=8.2),
        ]
    async def discover_series(self, page=1):
        return [DiscoverItem(tmdb_id=1399, type="Series", title="Dark Matter", vote_average=7.8)]


@pytest.fixture
def app_client(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.update(
        bearer_token=BEARER,
        jellyfin={"base_url": "http://jf", "api_key": "k", "user_id": "u"},
        tmdb={"api_key": "tk"},
    )
    cache = InMemoryCache()
    fake_jellyfin = FakeJellyfin()
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jellyfin
    app.dependency_overrides[deps.get_tmdb] = lambda: FakeTmdb()
    with TestClient(app) as c:
        c.store, c.cache, c.fake_jellyfin = store, cache, fake_jellyfin
        yield c


def test_recommend_splits_new_and_library_shelves(app_client):
    r = app_client.get("/recommend", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["llm_used"] is False
    shelves = {s["id"]: s for s in data["shelves"]}
    assert [i["title"] for i in shelves["new-for-you"]["items"]] == ["The Matrix", "Dark Matter"]
    assert all(i["status"] == "requestable" for i in shelves["new-for-you"]["items"])
    assert {i["title"] for i in shelves["from-library"]["items"]} == {"Blade Runner", "Severance"}
    assert all(i["status"] == "playable" for i in shelves["from-library"]["items"])


def test_recommend_is_cached(app_client):
    app_client.get("/recommend", headers=AUTH)
    app_client.get("/recommend", headers=AUTH)
    assert app_client.fake_jellyfin.movies_calls == 1


def test_recommend_uses_anthropic_when_configured(app_client):
    app_client.store.update(anthropic={"base_url": "http://anthropic", "api_key": "ak"})
    app_client.cache.store.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        content = [{"type": "text", "text": json.dumps([
            {"id": "tmdb:1399", "reason": "Claude stellt die Serienempfehlung nach vorn."},
            {"id": "tmdb:603", "reason": "Claude begründet Matrix natürlicher."},
            {"id": "library:m1", "reason": "Claude empfiehlt Blade Runner erneut."},
        ])}]
        assert "erfinde keine Titel" in prompt
        return httpx.Response(200, json={"content": content})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app_client.app.dependency_overrides[deps.get_http] = lambda: http
    r = app_client.get("/recommend", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["llm_used"] is True
    assert data["shelves"][0]["items"][0]["title"] == "Dark Matter"
    assert data["shelves"][0]["items"][0]["reason"] == "Claude stellt die Serienempfehlung nach vorn."
