"""Personal recommendations: M6 shelves plus optional M7 Claude reasons."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_bearer
from cache import TTL, Cache
from config import VaultConfig
from deps import get_cache, get_config, get_http, get_jellyfin, get_rating_store, get_tmdb
from models import DiscoverItem, LibraryItem, RecommendationResponse
from services.anthropic import AnthropicService
from services.jellyfin import JellyfinError, JellyfinService
from services.recommender import build_recommendations
from services.tmdb import TmdbError, TmdbService
from services.rating_store import RatingStore

router = APIRouter(prefix="/recommend", tags=["recommend"], dependencies=[Depends(require_bearer)])


def _cache_key(limit: int, llm_enabled: bool) -> str:
    return f"recommend:{limit}:llm:{int(llm_enabled)}"


@router.get("", response_model=RecommendationResponse)
async def recommend(
    limit: int = Query(12, ge=1, le=30),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    tmdb: TmdbService = Depends(get_tmdb),
    cache: Cache = Depends(get_cache),
    config: VaultConfig = Depends(get_config),
    http: httpx.AsyncClient = Depends(get_http),
    rating_store: RatingStore = Depends(get_rating_store),
) -> RecommendationResponse:
    llm_enabled = bool(config.anthropic.api_key)
    key = _cache_key(limit, llm_enabled)
    if (cached := await cache.get_json(key)) is not None:
        return RecommendationResponse.model_validate(cached)

    try:
        movies, series, latest_movies, latest_series = await _library_signals(jellyfin)
        discover_movies = await tmdb.discover_movies(1)
        discover_series = await tmdb.discover_series(1)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    library_items = _dedupe_items([*movies, *series, *latest_movies, *latest_series])
    discover_items = _dedupe_discover([*discover_movies, *discover_series])
    anthropic = AnthropicService(config.anthropic, http) if llm_enabled else None
    result = await build_recommendations(library_items, discover_items, anthropic, limit, rating_store.list())
    await cache.set_json(key, result.model_dump(), TTL.LLM if result.llm_used else TTL.TMDB_RECS)
    return result


async def _library_signals(jellyfin: JellyfinService) -> tuple[list[LibraryItem], ...]:
    # Broad but bounded snapshots: enough to infer a single-user taste profile
    # without introducing a separate ratings database.
    return (
        await jellyfin.movies(0, 100),
        await jellyfin.series(0, 100),
        await jellyfin.latest("Movie", 30),
        await jellyfin.latest("Series", 30),
    )


def _dedupe_items(items: list[LibraryItem]) -> list[LibraryItem]:
    out: list[LibraryItem] = []
    seen: set[str] = set()
    for item in items:
        if item.id not in seen:
            out.append(item)
            seen.add(item.id)
    return out


def _dedupe_discover(items: list[DiscoverItem]) -> list[DiscoverItem]:
    out: list[DiscoverItem] = []
    seen: set[tuple[str, int]] = set()
    for item in items:
        key = (item.type, item.tmdb_id)
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out
