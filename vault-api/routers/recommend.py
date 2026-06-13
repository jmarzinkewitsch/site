"""M6 recommendation shelves.

Two shelves mirror the product decision in the docs:
- `/recommend/library`: playable, already-owned items.
- `/recommend/discover`: requestable TMDB titles not already in Jellyfin.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_bearer
from cache import TTL, Cache
from deps import get_cache, get_jellyfin, get_tmdb
from models import LibraryItem, RecommendationItem
from services.jellyfin import JellyfinError, JellyfinService
from services.recommender import build_profile, recommend_discover, recommend_library, tmdb_genre_filter
from services.tmdb import TmdbError, TmdbService

router = APIRouter(prefix="/recommend", tags=["recommend"], dependencies=[Depends(require_bearer)])


def _library_key(kind: str, limit: int) -> str:
    return f"recommend:library:{kind}:{limit}"


def _discover_key(kind: str, limit: int) -> str:
    return f"recommend:discover:{kind}:{limit}"


async def _catalog(jellyfin: JellyfinService) -> list[LibraryItem]:
    movies = await jellyfin.movies(0, 500)
    series = await jellyfin.series(0, 500)
    return [*movies, *series]


@router.get("/library", response_model=list[RecommendationItem])
async def library_recommendations(
    type: str = Query("Movie"),
    limit: int = Query(16, ge=1, le=50),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[RecommendationItem]:
    kind = "Series" if type.lower() == "series" else "Movie"
    key = _library_key(kind, limit)
    if (cached := await cache.get_json(key)) is not None:
        return [RecommendationItem.model_validate(row) for row in cached]
    try:
        catalog = await _catalog(jellyfin)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    items = [item for item in catalog if item.type == kind]
    recs = recommend_library(items, limit)
    await cache.set_json(key, [r.model_dump() for r in recs], TTL.TMDB_RECS)
    return recs


@router.get("/discover", response_model=list[RecommendationItem])
async def discover_recommendations(
    type: str = Query("Movie"),
    limit: int = Query(16, ge=1, le=50),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    tmdb: TmdbService = Depends(get_tmdb),
    cache: Cache = Depends(get_cache),
) -> list[RecommendationItem]:
    kind = "Series" if type.lower() == "series" else "Movie"
    key = _discover_key(kind, limit)
    if (cached := await cache.get_json(key)) is not None:
        return [RecommendationItem.model_validate(row) for row in cached]
    try:
        catalog = await _catalog(jellyfin)
        profile = build_profile(catalog)
        genre_filter = tmdb_genre_filter(profile, kind)
        if kind == "Series":
            discovered = await tmdb.discover_series(1, with_genres=genre_filter)
        else:
            discovered = await tmdb.discover_movies(1, with_genres=genre_filter)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    owned = {item.tmdb_id for item in catalog if item.type == kind and item.tmdb_id is not None}
    recs = recommend_discover(discovered, owned, profile, limit)
    await cache.set_json(key, [r.model_dump() for r in recs], TTL.TMDB_RECS)
    return recs
