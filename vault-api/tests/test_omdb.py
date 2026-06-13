import httpx
import pytest

from config import ServiceConfig
from services.omdb import OmdbError, OmdbService, map_scores

CFG = ServiceConfig(api_key="omdbkey")

SAMPLE = {
    "Response": "True",
    "imdbRating": "9.3",
    "Metascore": "82",
    "Ratings": [
        {"Source": "Internet Movie Database", "Value": "9.3/10"},
        {"Source": "Rotten Tomatoes", "Value": "91%"},
        {"Source": "Metacritic", "Value": "82/100"},
    ],
}


def test_map_scores_full():
    scores = map_scores(SAMPLE)
    assert scores.imdb == 9.3
    assert scores.rotten_tomatoes == 91
    assert scores.metacritic == 82


def test_map_scores_handles_na_and_missing():
    scores = map_scores({"Response": "True", "imdbRating": "N/A", "Ratings": [
        {"Source": "Rotten Tomatoes", "Value": "55%"}]})
    assert scores.imdb is None
    assert scores.metacritic is None
    assert scores.rotten_tomatoes == 55


def test_map_scores_not_found_returns_none():
    assert map_scores({"Response": "False", "Error": "Incorrect IMDb ID."}) is None


def test_map_scores_all_empty_returns_none():
    assert map_scores({"Response": "True", "imdbRating": "N/A", "Metascore": "N/A"}) is None


def _svc(handler) -> OmdbService:
    return OmdbService(CFG, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_scores_sends_key_and_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["apikey"] == "omdbkey"
        assert request.url.params["i"] == "tt0111161"
        return httpx.Response(200, json=SAMPLE)

    scores = await _svc(handler).scores("tt0111161")
    assert scores.rotten_tomatoes == 91


async def test_error_status_raises():
    svc = _svc(lambda r: httpx.Response(500))
    with pytest.raises(OmdbError):
        await svc.scores("tt1")
