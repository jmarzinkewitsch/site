import httpx
import pytest

from services.arr import ArrError
from services.radarr import RadarrService
from services.sonarr import SonarrService


def _radarr(handler) -> RadarrService:
    return RadarrService("http://radarr", "k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _sonarr(handler) -> SonarrService:
    return SonarrService("http://sonarr", "k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_radarr_add_new_movie_searches():
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == "k"
        if request.url.path == "/api/v3/movie/lookup":
            assert request.url.params["term"] == "tmdb:603"
            return httpx.Response(200, json=[{"title": "The Matrix", "tmdbId": 603}])
        if request.url.path == "/api/v3/movie" and request.method == "POST":
            import json
            posted.update(json.loads(request.content))
            return httpx.Response(201, json={"id": 7, "title": "The Matrix"})
        return httpx.Response(404)

    result = await _radarr(handler).add(603, quality_profile_id=2, root_folder="/movies")
    assert result.status == "added"
    assert result.arr_id == 7
    assert posted["qualityProfileId"] == 2
    assert posted["rootFolderPath"] == "/movies"
    assert posted["addOptions"]["searchForMovie"] is True


async def test_radarr_add_existing_is_idempotent():
    def handler(request: httpx.Request) -> httpx.Response:
        # A lookup result carrying an id means it's already in Radarr.
        return httpx.Response(200, json=[{"id": 9, "title": "Dune", "tmdbId": 438631}])

    result = await _radarr(handler).add(438631)
    assert result.status == "already_exists"
    assert result.arr_id == 9


async def test_radarr_add_no_match_raises_404():
    handler = lambda r: httpx.Response(200, json=[])
    with pytest.raises(ArrError) as exc:
        await _radarr(handler).add(1)
    assert exc.value.status_code == 404


async def test_resolve_defaults_falls_back_to_first_profile_and_folder():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v3/movie/lookup":
            return httpx.Response(200, json=[{"title": "X", "tmdbId": 1}])
        if path == "/api/v3/qualityprofile":
            return httpx.Response(200, json=[{"id": 4, "name": "HD"}])
        if path == "/api/v3/rootfolder":
            return httpx.Response(200, json=[{"path": "/data/movies"}])
        if path == "/api/v3/movie" and request.method == "POST":
            import json
            body = json.loads(request.content)
            assert body["qualityProfileId"] == 4
            assert body["rootFolderPath"] == "/data/movies"
            return httpx.Response(201, json={"id": 1})
        return httpx.Response(404)

    # No explicit values and no admin defaults → first available are used.
    result = await _radarr(handler).add(1)
    assert result.status == "added"


async def test_queue_progress_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"records": [
            {"title": "A", "size": 100, "sizeleft": 25, "status": "downloading", "timeleft": "00:05:00"},
            {"title": "B", "size": 0, "sizeleft": 0, "status": "queued"},
        ]})

    items = await _radarr(handler).queue()
    assert items[0].title == "A"
    assert items[0].progress == 0.75
    assert items[0].type == "Movie"
    assert items[1].progress == 0.0


async def test_sonarr_add_new_series():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/series/lookup":
            assert request.url.params["term"] == "tvdb:81189"
            return httpx.Response(200, json=[{"title": "Breaking Bad", "tvdbId": 81189}])
        if request.url.path == "/api/v3/series" and request.method == "POST":
            import json
            assert json.loads(request.content)["addOptions"]["searchForMissingEpisodes"] is True
            return httpx.Response(201, json={"id": 3})
        return httpx.Response(404)

    result = await _sonarr(handler).add(81189, quality_profile_id=1, root_folder="/tv")
    assert result.status == "added"
    assert result.arr_id == 3


async def test_arr_error_status_raises():
    with pytest.raises(ArrError) as exc:
        await _radarr(lambda r: httpx.Response(500))._request("GET", "queue")
    assert exc.value.status_code == 500
