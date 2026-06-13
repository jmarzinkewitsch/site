"""Outward-facing DTOs: the vault-specific JSON the tvOS app decodes.

These are deliberately flat and client-friendly. The app never sees raw
Jellyfin/TMDB shapes — vault-api maps everything into these.
"""
from __future__ import annotations

from pydantic import BaseModel


class LibraryItem(BaseModel):
    id: str
    type: str  # "Movie" | "Series" | "Episode"
    title: str
    overview: str | None = None
    year: int | None = None
    genres: list[str] = []
    runtime_seconds: float | None = None
    community_rating: float | None = None  # ≈ IMDB (Jellyfin field)
    official_rating: str | None = None     # e.g. "FSK 16"
    poster_url: str | None = None
    backdrop_url: str | None = None
    # Playback state (from Jellyfin UserData)
    played: bool = False
    played_percentage: float | None = None
    resume_position_seconds: float = 0.0
    # Episode context (None for movies/series)
    series_id: str | None = None
    series_name: str | None = None
    season_id: str | None = None
    index_number: int | None = None
    parent_index_number: int | None = None
    episode_code: str | None = None
    tmdb_id: int | None = None  # from Jellyfin ProviderIds, for library↔TMDB matching


class DiscoverItem(BaseModel):
    """A TMDB title — may or may not be in the library yet."""
    tmdb_id: int
    type: str  # "Movie" | "Series"
    title: str
    year: int | None = None
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    vote_average: float | None = None


class SearchItem(BaseModel):
    title: str
    type: str  # "Movie" | "Series"
    year: int | None = None
    poster_url: str | None = None
    source: str          # "library" | "discover"
    status: str          # "playable" | "requestable"
    library_id: str | None = None  # set when status == "playable"
    tmdb_id: int | None = None      # set when status == "requestable"


class RequestMovieBody(BaseModel):
    tmdb_id: int
    quality_profile_id: int | None = None  # falls back to the admin default
    root_folder: str | None = None


class RequestSeriesBody(BaseModel):
    tmdb_id: int
    quality_profile_id: int | None = None
    root_folder: str | None = None


class RequestResult(BaseModel):
    ok: bool
    status: str  # "added" | "already_exists"
    title: str
    arr_id: int | None = None
    detail: str | None = None


class QueueItem(BaseModel):
    title: str
    type: str  # "Movie" | "Series"
    progress: float  # 0..1 (1 - size_left/size)
    status: str | None = None
    time_left: str | None = None



class StreamInfo(BaseModel):
    """What the player needs. The URL points straight at Jellyfin (LAN) and
    carries the api_key — see the streaming note in architecture-api-first.md."""
    url: str
    container: str | None = None
    runtime_seconds: float | None = None


class ProgressUpdate(BaseModel):
    position_seconds: float
    is_paused: bool = False


class ServiceStatus(BaseModel):
    name: str
    configured: bool
    ok: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    services: list[ServiceStatus]
