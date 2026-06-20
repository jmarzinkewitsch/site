"""Tests for the "Was schauen wir?" picker: profiles + picker endpoint."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from doubles import InMemoryCache
from main import create_app
from models import DiscoverItem, LibraryItem, PersonaProfile
from services.profile_store import ProfileStore
from services.rating_store import RatingStore

BEARER = "picker-token"
AUTH = {"Authorization": f"Bearer {BEARER}"}


# ──────────────────────────────────────────────────────────────────────────────
# Shared test fixtures
# ──────────────────────────────────────────────────────────────────────────────


class FakeJellyfin:
    def __init__(self) -> None:
        self.shelf_calls = 0

    async def shelf(self, *, include_type="Movie", sort="top_rated", genres=None, unplayed=False, limit=16):
        self.shelf_calls += 1
        items = [
            LibraryItem(
                id="m1",
                type="Movie",
                title="Blade Runner",
                year=1982,
                genres=["Sci-Fi"],
                community_rating=8.1,
                runtime_seconds=7000,
                tmdb_id=78,
                overview="A noir sci-fi classic set in the future.",
            ),
            LibraryItem(
                id="m2",
                type="Movie",
                title="Interstellar",
                year=2014,
                genres=["Sci-Fi", "Drama"],
                community_rating=8.6,
                runtime_seconds=10260,
                tmdb_id=157336,
                overview="Explorers travel through a wormhole in space.",
            ),
        ]
        return [i for i in items if include_type in (i.type, "Movie", "Series")]

    # Other methods the router might call via deps
    async def movies(self, start=0, limit=100):
        return []

    async def series(self, start=0, limit=100):
        return []

    async def latest(self, include_type, limit=30):
        return []


class FakeTmdb:
    async def discover_movies(self, page=1):
        return [
            DiscoverItem(
                tmdb_id=603,
                type="Movie",
                title="The Matrix",
                year=1999,
                overview="A computer hacker learns about the true nature of reality.",
                vote_average=8.2,
                genre_ids=[878, 28],
            )
        ]

    async def discover_series(self, page=1):
        return [
            DiscoverItem(
                tmdb_id=1399,
                type="Series",
                title="Game of Thrones",
                year=2011,
                overview="Nine noble families fight for control over the mythical lands of Westeros.",
                vote_average=8.4,
                genre_ids=[18, 10765],
            )
        ]

    async def discover_movies_by_genres(self, genre_ids, page=1):
        return await self.discover_movies(page)

    async def discover_series_by_genres(self, genre_ids, page=1):
        return await self.discover_series(page)

    async def trending_movies(self, page=1):
        return []

    async def trending_series(self, page=1):
        return []


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
    profile_store = ProfileStore(tmp_path / "profiles.db")
    fake_jellyfin = FakeJellyfin()

    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jellyfin
    app.dependency_overrides[deps.get_tmdb] = lambda: FakeTmdb()
    app.dependency_overrides[deps.get_rating_store] = lambda: rating_store
    app.dependency_overrides[deps.get_profile_store] = lambda: profile_store

    with TestClient(app) as c:
        c.store = store
        c.cache = cache
        c.fake_jellyfin = fake_jellyfin
        c.rating_store = rating_store
        c.profile_store = profile_store
        yield c


# ──────────────────────────────────────────────────────────────────────────────
# Profile tests
# ──────────────────────────────────────────────────────────────────────────────


def test_profiles_get_returns_defaults(app_client):
    r = app_client.get("/profiles", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    persons = {p["person"] for p in data}
    assert persons == {"janno", "tanno"}
    # All must have fear_comfort
    for p in data:
        assert "fear_comfort" in p
        assert "favorite_genres" in p


def test_profiles_put_and_get_round_trip(app_client):
    # Upsert janno
    body = {"person": "janno", "favorite_genres": ["Sci-Fi", "Drama"], "fear_comfort": 7}
    r = app_client.put("/profiles/janno", headers=AUTH, json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["person"] == "janno"
    assert data["favorite_genres"] == ["Sci-Fi", "Drama"]
    assert data["fear_comfort"] == 7

    # GET returns persisted value
    r2 = app_client.get("/profiles", headers=AUTH)
    assert r2.status_code == 200
    profiles = {p["person"]: p for p in r2.json()}
    assert profiles["janno"]["favorite_genres"] == ["Sci-Fi", "Drama"]
    assert profiles["janno"]["fear_comfort"] == 7


def test_profiles_put_invalid_person(app_client):
    body = {"person": "stranger", "favorite_genres": [], "fear_comfort": 5}
    r = app_client.put("/profiles/stranger", headers=AUTH, json=body)
    assert r.status_code == 422


def test_profiles_put_person_mismatch(app_client):
    body = {"person": "tanno", "favorite_genres": [], "fear_comfort": 5}
    r = app_client.put("/profiles/janno", headers=AUTH, json=body)
    assert r.status_code == 422


def test_profiles_put_updates_tanno(app_client):
    body = {"person": "tanno", "favorite_genres": ["Horror", "Thriller"], "fear_comfort": 3}
    r = app_client.put("/profiles/tanno", headers=AUTH, json=body)
    assert r.status_code == 200
    assert r.json()["fear_comfort"] == 3
    assert "Horror" in r.json()["favorite_genres"]


# ──────────────────────────────────────────────────────────────────────────────
# Picker endpoint tests
# ──────────────────────────────────────────────────────────────────────────────


def test_picker_happy_path_with_mocked_curate_picks(app_client):
    """Mocked curate_picks returns chosen ids → response has correct source/status/reason."""
    app_client.store.update(anthropic={"base_url": "http://anthropic", "api_key": "ak"})

    llm_response = {
        "library_pick": {"id": "library:m1", "reason": "Ein atmosphärischer Sci-Fi-Klassiker."},
        "discover_pick": {"id": "tmdb:603", "reason": "Matrix ist zeitloser Kult."},
        "alternatives": [
            {"id": "library:m2", "reason": "Interstellar begeistert mit Raumfahrt-Drama."},
            {"id": "tmdb:1399", "reason": "Game of Thrones für epische Serienfans."},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # Verify it uses sonnet-4-6
        assert "claude-sonnet-4-6" in body.get("model", "")
        content = [{"type": "text", "text": json.dumps(llm_response)}]
        return httpx.Response(200, json={"content": content})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app_client.app.dependency_overrides[deps.get_http] = lambda: http

    r = app_client.post("/recommend/picker", headers=AUTH, json={"profile": "both"})
    assert r.status_code == 200
    data = r.json()
    assert data["llm_used"] is True

    # library_pick is from library
    assert data["library_pick"] is not None
    lp = data["library_pick"]
    assert lp["source"] == "library"
    assert lp["status"] == "playable"
    assert lp["library_id"] == "m1"
    assert lp["tmdb_id"] is None
    assert lp["reason"] == "Ein atmosphärischer Sci-Fi-Klassiker."
    assert lp["title"] == "Blade Runner"

    # discover_pick is from discover
    assert data["discover_pick"] is not None
    dp = data["discover_pick"]
    assert dp["source"] == "discover"
    assert dp["status"] == "requestable"
    assert dp["tmdb_id"] == 603
    assert dp["library_id"] is None
    assert dp["reason"] == "Matrix ist zeitloser Kult."
    assert dp["title"] == "The Matrix"

    # alternatives present
    assert len(data["alternatives"]) >= 1


def test_picker_fallback_when_anthropic_raises(app_client):
    """When AnthropicError is raised, fallback kicks in and llm_used=False."""
    app_client.store.update(anthropic={"base_url": "http://anthropic", "api_key": "ak"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Internal server error"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app_client.app.dependency_overrides[deps.get_http] = lambda: http

    r = app_client.post("/recommend/picker", headers=AUTH, json={"profile": "both"})
    assert r.status_code == 200
    data = r.json()
    assert data["llm_used"] is False
    # Still returns picks via fallback
    assert data["library_pick"] is not None or data["discover_pick"] is not None


def test_picker_no_anthropic_uses_fallback(app_client):
    """Without Anthropic configured, fallback is used, llm_used=False."""
    r = app_client.post("/recommend/picker", headers=AUTH, json={"profile": "both"})
    assert r.status_code == 200
    data = r.json()
    assert data["llm_used"] is False
    assert data["library_pick"] is not None
    assert data["library_pick"]["source"] == "library"
    assert data["library_pick"]["status"] == "playable"
    assert data["discover_pick"] is not None
    assert data["discover_pick"]["source"] == "discover"
    assert data["discover_pick"]["status"] == "requestable"


def test_picker_exclude_ids_filters_out_items(app_client):
    """Items in exclude_ids must not appear in any pick."""
    r = app_client.post(
        "/recommend/picker",
        headers=AUTH,
        json={"profile": "both", "exclude_ids": ["library:m1", "library:m2", "tmdb:603", "tmdb:1399"]},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["library_pick"] is None
    # all library excluded → no library pick
    # all discover excluded → no discover pick
    assert data["discover_pick"] is None


def test_picker_length_series_excludes_movies(app_client):
    """length=series must exclude Movie candidates."""
    r = app_client.post("/recommend/picker", headers=AUTH, json={"profile": "both", "length": "series"})
    assert r.status_code == 200
    data = r.json()
    # library has only movies, so library_pick should be None
    assert data["library_pick"] is None
    # discover should return the series
    if data["discover_pick"]:
        assert data["discover_pick"]["type"] == "Series"


def test_picker_janno_profile(app_client):
    """profile=janno is accepted."""
    r = app_client.post("/recommend/picker", headers=AUTH, json={"profile": "janno"})
    assert r.status_code == 200


def test_picker_tanno_profile(app_client):
    """profile=tanno is accepted."""
    r = app_client.post("/recommend/picker", headers=AUTH, json={"profile": "tanno"})
    assert r.status_code == 200


def test_picker_requires_auth(tmp_path):
    """Unauthenticated requests must be rejected (401) when bearer token is set."""
    from main import create_app as _create_app

    store = ConfigStore(tmp_path / "config.json")
    store.update(bearer_token="some-token")
    profile_store = ProfileStore(tmp_path / "profiles.db")
    rating_store = RatingStore(tmp_path / "ratings.db")

    app = _create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_profile_store] = lambda: profile_store
    app.dependency_overrides[deps.get_rating_store] = lambda: rating_store
    with TestClient(app) as c:
        r = c.post("/recommend/picker", json={"profile": "both"})
    assert r.status_code == 401


def test_picker_response_shape(app_client):
    """Verify all expected fields exist in the response."""
    r = app_client.post("/recommend/picker", headers=AUTH, json={"profile": "both"})
    assert r.status_code == 200
    data = r.json()
    assert "library_pick" in data
    assert "discover_pick" in data
    assert "alternatives" in data
    assert "llm_used" in data
    if data["library_pick"]:
        lp = data["library_pick"]
        for field in ("id", "title", "type", "source", "status", "reason"):
            assert field in lp, f"missing field {field} in library_pick"
