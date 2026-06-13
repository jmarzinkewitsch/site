"""Outward-facing DTOs: the vault-specific JSON the tvOS app decodes.

These are deliberately flat and client-friendly. The app never sees raw
Jellyfin/TMDB shapes — vault-api maps everything into these.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExternalScores(BaseModel):
    """Aggregate critic/audience scores from OMDb (M5, optional)."""
    imdb: float | None = None            # 0–10
    rotten_tomatoes: int | None = None   # 0–100 (%)
    metacritic: int | None = None        # 0–100
    source: str = "omdb"


class LibraryItem(BaseModel):
    id: str
    type: str  # "Movie" | "Series" | "Episode"
    title: str
    overview: str | None = None
    year: int | None = None
    genres: list[str] = []
    runtime_seconds: float | None = None
    community_rating: float | None = None  # ≈ IMDB aggregate (Jellyfin field)
    critic_rating: float | None = None      # ≈ RT (Jellyfin CriticRating, 0–100)
    user_rating: float | None = None        # this user's own 0–10 rating
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
    imdb_id: str | None = None  # from Jellyfin ProviderIds, for OMDb score lookup
    external_scores: ExternalScores | None = None  # filled in item detail when OMDb is on


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


class RecommendationItem(BaseModel):
    """One M6 recommendation. Exactly one of item/discover is set.

    `item` is playable library content; `discover` is requestable TMDB content.
    The reason is deterministic for now; M7 can replace or enrich it with LLM text.
    """
    item: LibraryItem | None = None
    discover: DiscoverItem | None = None
    score: float | None = None
    reason: str


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


class RatingUpdate(BaseModel):
    rating: float = Field(ge=0, le=10)  # out-of-range → 422 from FastAPI


class ServiceStatus(BaseModel):
    name: str
    configured: bool
    ok: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    services: list[ServiceStatus]
