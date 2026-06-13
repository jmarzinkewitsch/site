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
