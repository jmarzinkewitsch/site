"""Discovery via TMDB — popular movies/series to browse and request.

Taste-based filtering and the two-shelf recommendation split arrive in M6; M4
serves plain TMDB popularity so the request flow has something to act on.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_bearer
from cache import TTL, Cache
from deps import get_cache, get_tmdb
from models import DiscoverItem
from services.tmdb import TmdbError, TmdbService

router = APIRouter(prefix="/discover", tags=["discover"], dependencies=[Depends(require_bearer)])


async def _cached(cache: Cache, key: str, fetch) -> list[DiscoverItem]:
    if (cached := await cache.get_json(key)) is not None:
        return [DiscoverItem.model_validate(row) for row in cached]
    try:
        items = await fetch()
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    await cache.set_json(key, [i.model_dump() for i in items], TTL.TMDB_RECS)
    return items


@router.get("/movies", response_model=list[DiscoverItem])
async def discover_movies(
    page: int = Query(1, ge=1, le=500),
    tmdb: TmdbService = Depends(get_tmdb),
    cache: Cache = Depends(get_cache),
) -> list[DiscoverItem]:
    return await _cached(cache, f"discover:movies:{page}", lambda: tmdb.discover_movies(page))


@router.get("/series", response_model=list[DiscoverItem])
async def discover_series(
    page: int = Query(1, ge=1, le=500),
    tmdb: TmdbService = Depends(get_tmdb),
    cache: Cache = Depends(get_cache),
) -> list[DiscoverItem]:
    return await _cached(cache, f"discover:series:{page}", lambda: tmdb.discover_series(page))
