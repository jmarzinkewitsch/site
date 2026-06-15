"""TMDB client + mapping.

TMDB is the discovery/search backbone (architecture-api-first.md): vault-api
searches TMDB and hands the hit's `tmdbId` to Radarr; for series TMDB's
`external_ids` yields the `tvdbId` Sonarr needs. Uses the v3 API with the key as
a query param. Pure mappers (`map_movie`, `map_series`) are unit-tested.
"""
from __future__ import annotations

import httpx

from config import ServiceConfig
from models import DiscoverItem

DEFAULT_BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"


class TmdbError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _year(date: str | None) -> int | None:
    if not date or len(date) < 4 or not date[:4].isdigit():
        return None
    return int(date[:4])


def _image(path: str | None, size: str) -> str | None:
    return f"{IMAGE_BASE}/{size}{path}" if path else None


def youtube_trailer_url(raw: dict) -> str | None:
    """Pick the best YouTube trailer URL from a TMDB /videos response."""
    videos = raw.get("results")
    if not isinstance(videos, list):
        return None

    def is_youtube_trailer(video: dict) -> bool:
        return (
            video.get("site") == "YouTube"
            and video.get("type") == "Trailer"
            and isinstance(video.get("key"), str)
            and bool(video.get("key"))
        )

    trailers = [video for video in videos if isinstance(video, dict) and is_youtube_trailer(video)]
    if not trailers:
        return None

    official = [video for video in trailers if video.get("official") is True]
    selected = (official or trailers)[0]
    return f"https://www.youtube.com/watch?v={selected['key']}"


def map_movie(raw: dict) -> DiscoverItem:
    return DiscoverItem(
        tmdb_id=raw["id"],
        type="Movie",
        title=raw.get("title") or raw.get("original_title") or "",
        year=_year(raw.get("release_date")),
        overview=raw.get("overview"),
        poster_url=_image(raw.get("poster_path"), "w500"),
        backdrop_url=_image(raw.get("backdrop_path"), "w1280"),
        vote_average=raw.get("vote_average"),
    )


def map_series(raw: dict) -> DiscoverItem:
    return DiscoverItem(
        tmdb_id=raw["id"],
        type="Series",
        title=raw.get("name") or raw.get("original_name") or "",
        year=_year(raw.get("first_air_date")),
        overview=raw.get("overview"),
        poster_url=_image(raw.get("poster_path"), "w500"),
        backdrop_url=_image(raw.get("backdrop_path"), "w1280"),
        vote_average=raw.get("vote_average"),
    )


class TmdbService:
    def __init__(self, cfg: ServiceConfig, client: httpx.AsyncClient) -> None:
        self._key = cfg.api_key
        self._base = (cfg.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._client = client

    async def _get(self, path: str, params: dict | None = None) -> dict:
        query = {"api_key": self._key, **(params or {})}
        try:
            response = await self._client.get(f"{self._base}/{path.lstrip('/')}", params=query)
        except httpx.HTTPError as exc:
            raise TmdbError(f"TMDB nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise TmdbError(f"TMDB {response.status_code}", response.status_code)
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def search_movies(self, query: str) -> list[DiscoverItem]:
        data = await self._get("search/movie", {"query": query, "include_adult": "false"})
        return [map_movie(r) for r in data.get("results", [])]

    async def search_series(self, query: str) -> list[DiscoverItem]:
        data = await self._get("search/tv", {"query": query, "include_adult": "false"})
        return [map_series(r) for r in data.get("results", [])]

    async def discover_movies(self, page: int = 1) -> list[DiscoverItem]:
        data = await self._get("discover/movie", {"sort_by": "popularity.desc", "page": page})
        return [map_movie(r) for r in data.get("results", [])]

    async def discover_series(self, page: int = 1) -> list[DiscoverItem]:
        data = await self._get("discover/tv", {"sort_by": "popularity.desc", "page": page})
        return [map_series(r) for r in data.get("results", [])]

    async def trailer_url(self, media_type: str, tmdb_id: int) -> str | None:
        """Return a watch URL for the best YouTube trailer in TMDB videos."""
        kind = "tv" if media_type == "Series" else "movie"
        data = await self._get(f"{kind}/{tmdb_id}/videos")
        return youtube_trailer_url(data)

    async def series_tvdb_id(self, tmdb_id: int) -> int | None:
        """Sonarr keys series by tvdbId; TMDB exposes it via external_ids."""
        data = await self._get(f"tv/{tmdb_id}/external_ids")
        tvdb = data.get("tvdb_id")
        return int(tvdb) if tvdb else None

    async def ping(self) -> bool:
        await self._get("configuration")
        return True
