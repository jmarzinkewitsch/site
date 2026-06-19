"""M7 recommendation route: algorithmic shelves with optional Claude polish."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from doubles import InMemoryCache
from main import create_app
from models import DiscoverItem, LibraryItem
from services.rating_store import RatingStore

BEARER = "m7-token"
AUTH = {"Authorization": f"Bearer {BEARER}"}


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
    rating_store = RatingStore(tmp_path / "ratings.db")
    rating_store.upsert(item_id="m1", title="Blade Runner", type="Movie", year=1982, tmdb_id=78, janno_rating=9, tanno_rating=7, tanno_fear_factor=2)
    fake_jellyfin = FakeJellyfin()
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jellyfin
    app.dependency_overrides[deps.get_tmdb] = lambda: FakeTmdb()
    app.dependency_overrides[deps.get_rating_store] = lambda: rating_store
    with TestClient(app) as c:
        c.store, c.cache, c.fake_jellyfin, c.rating_store = store, cache, fake_jellyfin, rating_store
        yield c


def test_recommend_returns_profile_shelves_with_scores(app_client):
    r = app_client.get("/recommend", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["llm_used"] is False
    shelves = {s["id"]: s for s in data["shelves"]}
    assert set(shelves) == {"both", "janno", "tanno"}
    assert shelves["both"]["title"] == "Für euch beide"
    assert shelves["janno"]["title"] == "Jannos Profil"
    assert shelves["tanno"]["title"] == "Tannos Profil"

    both_items = shelves["both"]["items"]
    assert {i["title"] for i in both_items} >= {"The Matrix", "Dark Matter", "Blade Runner"}
    matrix = next(i for i in both_items if i["title"] == "The Matrix")
    assert matrix["status"] == "requestable"
    assert matrix["community_rating"] == 8.2
    assert matrix["match_score"] is not None
    assert matrix["profile"] == "both"
    assert matrix["category_tags"]

    blade = next(i for i in both_items if i["title"] == "Blade Runner")
    assert blade["status"] == "playable"
    assert blade["community_rating"] == 8.1
    assert blade["janno_score"] == 90
    assert blade["tanno_score"] == 70
    assert blade["fear_factor"] == 2


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
    assert data["shelves"][0]["items"]


def test_recommend_accepts_anthropic_json_wrapped_in_code_fence(app_client):
    app_client.store.update(anthropic={"base_url": "http://anthropic", "api_key": "ak"})
    app_client.cache.store.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        content = [{"type": "text", "text": '```json\n[{"id":"tmdb:603","reason":"Passt als stilvoller Sci-Fi-Abend."}]\n```'}]
        return httpx.Response(200, json={"content": content})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app_client.app.dependency_overrides[deps.get_http] = lambda: http
    r = app_client.get("/recommend", headers=AUTH)

    assert r.status_code == 200
    data = r.json()
    assert data["llm_used"] is True
    matrix = next(i for s in data["shelves"] for i in s["items"] if i["title"] == "The Matrix")
    assert matrix["reason"] == "Passt als stilvoller Sci-Fi-Abend."
