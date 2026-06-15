import asyncio
import httpx
import pytest

from config import ServiceConfig
from services.tmdb import TmdbError, TmdbService, map_movie, map_series, youtube_trailer_url

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


def test_search_movies_sends_key_and_maps():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/search/movie"
            assert request.url.params["api_key"] == "tmdbkey"
            assert request.url.params["query"] == "matrix"
            return httpx.Response(200, json={"results": [{"id": 603, "title": "The Matrix"}]})

        items = await _svc(handler).search_movies("matrix")
        assert items[0].tmdb_id == 603

    asyncio.run(run())


def test_series_tvdb_id():
    async def run():
        svc = _svc(lambda r: httpx.Response(200, json={"tvdb_id": 81189}))
        assert await svc.series_tvdb_id(1396) == 81189

    asyncio.run(run())


def test_series_tvdb_id_missing_returns_none():
    async def run():
        svc = _svc(lambda r: httpx.Response(200, json={"tvdb_id": None}))
        assert await svc.series_tvdb_id(1396) is None

    asyncio.run(run())


def test_error_status_raises():
    async def run():
        svc = _svc(lambda r: httpx.Response(401, json={}))
        with pytest.raises(TmdbError) as exc:
            await svc.search_movies("x")
        assert exc.value.status_code == 401

    asyncio.run(run())


def test_youtube_trailer_url_prefers_official_youtube_trailer():
    url = youtube_trailer_url({"results": [
        {"site": "YouTube", "type": "Teaser", "key": "tease", "official": True},
        {"site": "YouTube", "type": "Trailer", "key": "fan", "official": False},
        {"site": "YouTube", "type": "Trailer", "key": "official", "official": True},
    ]})
    assert url == "https://www.youtube.com/watch?v=official"


def test_youtube_trailer_url_ignores_non_youtube():
    assert youtube_trailer_url({"results": [{"site": "Vimeo", "type": "Trailer", "key": "x"}]}) is None


def test_trailer_url_uses_movie_videos_endpoint():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/movie/603/videos"
            assert request.url.params["api_key"] == "tmdbkey"
            return httpx.Response(200, json={"results": [{"site": "YouTube", "type": "Trailer", "key": "abc"}]})

        assert await _svc(handler).trailer_url("Movie", 603) == "https://www.youtube.com/watch?v=abc"

    asyncio.run(run())
