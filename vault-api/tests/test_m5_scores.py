"""Item-detail enrichment with OMDb scores (M5)."""
import httpx
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from doubles import InMemoryCache
from main import create_app
from models import LibraryItem

BEARER = "m5-token"
AUTH = {"Authorization": f"Bearer {BEARER}"}

OMDB_SAMPLE = {
    "Response": "True", "imdbRating": "8.7",
    "Ratings": [{"Source": "Rotten Tomatoes", "Value": "88%"}],
}


class FakeJellyfin:
    def __init__(self): self.item_calls = 0
    async def item(self, item_id):
        self.item_calls += 1
        return LibraryItem(id=item_id, type="Movie", title="The Matrix",
                           community_rating=8.2, imdb_id="tt0133093", tmdb_id=603)


def _enrichment_http() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/movie/603/videos":
            return httpx.Response(200, json={"results": [{"site": "YouTube", "type": "Trailer", "key": "abc", "official": True}]})
        if request.url.params.get("i") == "tt0133093":
            return httpx.Response(200, json=OMDB_SAMPLE)
        return httpx.Response(200, json={"Response": "False"})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _client(tmp_path, omdb_configured: bool, cache, fake_jf, http, tmdb_configured: bool = False):
    store = ConfigStore(tmp_path / "config.json")
    sections = {
        "bearer_token": BEARER,
        "jellyfin": {"base_url": "http://jf", "api_key": "k", "user_id": "u"},
    }
    if omdb_configured:
        sections["omdb"] = {"api_key": "ok"}
    if tmdb_configured:
        sections["tmdb"] = {"api_key": "tmdbkey"}
    store.update(**sections)
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_http] = lambda: http
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jf
    return TestClient(app)


def test_item_detail_includes_omdb_scores(tmp_path):
    cache, fake_jf, http = InMemoryCache(), FakeJellyfin(), _enrichment_http()
    with _client(tmp_path, True, cache, fake_jf, http) as c:
        r = c.get("/library/item/m1", headers=AUTH)
        assert r.status_code == 200
        scores = r.json()["external_scores"]
        assert scores["imdb"] == 8.7
        assert scores["rotten_tomatoes"] == 88
        # Scores are cached separately by IMDB id (7d TTL).
        assert "omdb:tt0133093" in cache.store


def test_item_detail_without_omdb_has_no_scores(tmp_path):
    cache, fake_jf, http = InMemoryCache(), FakeJellyfin(), _enrichment_http()
    with _client(tmp_path, False, cache, fake_jf, http) as c:
        r = c.get("/library/item/m1", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["external_scores"] is None
        assert "omdb:tt0133093" not in cache.store


def test_item_detail_includes_tmdb_trailer_url(tmp_path):
    cache, fake_jf, http = InMemoryCache(), FakeJellyfin(), _enrichment_http()
    with _client(tmp_path, False, cache, fake_jf, http, tmdb_configured=True) as c:
        r = c.get("/library/item/m1", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["trailer_url"] == "https://www.youtube.com/watch?v=abc"
        assert cache.store["tmdb:trailer:Movie:603"] == {"url": "https://www.youtube.com/watch?v=abc"}


def test_item_detail_without_tmdb_has_no_trailer_url(tmp_path):
    cache, fake_jf, http = InMemoryCache(), FakeJellyfin(), _enrichment_http()
    with _client(tmp_path, False, cache, fake_jf, http, tmdb_configured=False) as c:
        r = c.get("/library/item/m1", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["trailer_url"] is None
        assert "tmdb:trailer:Movie:603" not in cache.store
