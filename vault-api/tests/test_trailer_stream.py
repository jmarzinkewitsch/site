import httpx
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from doubles import InMemoryCache
from main import create_app
from models import LibraryItem

BEARER = "trailer-token"
AUTH = {"Authorization": f"Bearer {BEARER}"}


class FakeJellyfin:
    def __init__(self, item):
        self.item_obj = item
        self.item_calls = 0

    async def item(self, item_id):
        self.item_calls += 1
        return self.item_obj


class FakeYoutubeDL:
    calls = 0

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=False):
        type(self).calls += 1
        assert download is False
        return {
            "formats": [
                {"format_id": "137", "url": "https://cdn/video-only.mp4", "ext": "mp4", "vcodec": "avc1", "acodec": "none"},
                {"format_id": "22", "url": "https://cdn/trailer.mp4", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a"},
            ]
        }


def _http():
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(404)))


def _client(tmp_path, cache, fake_jf):
    store = ConfigStore(tmp_path / "config.json")
    store.update(
        bearer_token=BEARER,
        jellyfin={"base_url": "http://jf", "api_key": "k", "user_id": "u"},
    )
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_http] = _http
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jf
    return TestClient(app)


def test_trailer_stream_resolves_and_caches_yt_dlp(monkeypatch, tmp_path):
    FakeYoutubeDL.calls = 0
    monkeypatch.setattr("routers.library.yt_dlp.YoutubeDL", FakeYoutubeDL)
    cache = InMemoryCache()
    item = LibraryItem(id="m1", type="Movie", title="Movie", trailer_url="https://youtube/watch?v=x")
    with _client(tmp_path, cache, FakeJellyfin(item)) as c:
        r = c.get("/library/item/m1/trailer-stream", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"url": "https://cdn/trailer.mp4", "container": "mp4"}
        assert cache.store["trailer:stream:m1"] == {"url": "https://cdn/trailer.mp4", "container": "mp4"}

        r = c.get("/library/item/m1/trailer-stream", headers=AUTH)
        assert r.status_code == 200
        assert FakeYoutubeDL.calls == 1


def test_trailer_stream_without_trailer_returns_404(monkeypatch, tmp_path):
    monkeypatch.setattr("routers.library.yt_dlp.YoutubeDL", FakeYoutubeDL)
    cache = InMemoryCache()
    item = LibraryItem(id="m1", type="Movie", title="Movie")
    with _client(tmp_path, cache, FakeJellyfin(item)) as c:
        r = c.get("/library/item/m1/trailer-stream", headers=AUTH)
        assert r.status_code == 404
        assert "trailer:stream:m1" not in cache.store
