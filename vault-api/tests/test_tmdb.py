import httpx
import pytest

from config import ServiceConfig
from services.tmdb import TmdbError, TmdbService, map_movie, map_series

CFG = ServiceConfig(api_key="tmdbkey")


def test_map_movie():
    item = map_movie({
        "id": 603, "title": "The Matrix", "release_date": "1999-03-31",
        "overview": "Neo.", "poster_path": "/p.jpg", "backdrop_path": "/b.jpg",
        "vote_average": 8.2,
    })
    assert item.tmdb_id == 603
    assert item.type == "Movie"
    assert item.title == "The Matrix"
    assert item.year == 1999
    assert item.poster_url == "https://image.tmdb.org/t/p/w500/p.jpg"
    assert item.vote_average == 8.2


def test_map_series_uses_name_and_first_air_date():
    item = map_series({"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20"})
    assert item.type == "Series"
    assert item.title == "Breaking Bad"
    assert item.year == 2008


def test_map_handles_missing_fields():
    item = map_movie({"id": 1, "title": "X"})
    assert item.year is None
    assert item.poster_url is None


def _svc(handler) -> TmdbService:
    return TmdbService(CFG, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_search_movies_sends_key_and_maps():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/search/movie"
        assert request.url.params["api_key"] == "tmdbkey"
        assert request.url.params["query"] == "matrix"
        return httpx.Response(200, json={"results": [{"id": 603, "title": "The Matrix"}]})

    items = await _svc(handler).search_movies("matrix")
    assert items[0].tmdb_id == 603


async def test_series_tvdb_id():
    svc = _svc(lambda r: httpx.Response(200, json={"tvdb_id": 81189}))
    assert await svc.series_tvdb_id(1396) == 81189


async def test_series_tvdb_id_missing_returns_none():
    svc = _svc(lambda r: httpx.Response(200, json={"tvdb_id": None}))
    assert await svc.series_tvdb_id(1396) is None


async def test_error_status_raises():
    svc = _svc(lambda r: httpx.Response(401, json={}))
    with pytest.raises(TmdbError) as exc:
        await svc.search_movies("x")
    assert exc.value.status_code == 401
