"""Library endpoints — the read path the app's browse UI hits.

Reads are cached (Redis) with the TTLs from the architecture doc; a progress
write invalidates the affected caches so watched/resume state doesn't go stale.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_bearer
from cache import TTL, Cache
from config import VaultConfig
from deps import get_cache, get_config, get_http, get_jellyfin
from models import ExternalScores, LibraryItem, ProgressUpdate, RatingUpdate
from services.jellyfin import JellyfinError, JellyfinService
from services.omdb import OmdbError, OmdbService

router = APIRouter(prefix="/library", tags=["library"], dependencies=[Depends(require_bearer)])


def _continue_key() -> str:
    return "lib:continue"


def _list_key(kind: str, start: int, limit: int) -> str:
    return f"lib:{kind}:{start}:{limit}"


def _item_key(item_id: str) -> str:
    return f"lib:item:{item_id}"


def _seasons_key(series_id: str) -> str:
    return f"lib:series:{series_id}:seasons"


def _episodes_key(series_id: str, season_id: str) -> str:
    return f"lib:series:{series_id}:season:{season_id}:episodes"


async def _cached_list(cache, key, ttl, fetch) -> list[LibraryItem]:
    if (cached := await cache.get_json(key)) is not None:
        return [LibraryItem.model_validate(row) for row in cached]
    try:
        items = await fetch()
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    await cache.set_json(key, [i.model_dump() for i in items], ttl)
    return items


@router.get("/movies", response_model=list[LibraryItem])
async def movies(
    start: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    return await _cached_list(cache, _list_key("movies", start, limit), TTL.LIBRARY,
                              lambda: jellyfin.movies(start, limit))


@router.get("/series", response_model=list[LibraryItem])
async def series(
    start: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    return await _cached_list(cache, _list_key("series", start, limit), TTL.LIBRARY,
                              lambda: jellyfin.series(start, limit))


@router.get("/continue", response_model=list[LibraryItem])
async def continue_watching(
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    # Short TTL: resume positions move while the user watches.
    return await _cached_list(cache, _continue_key(), 30,
                              lambda: jellyfin.continue_watching())


@router.get("/series/{series_id}/seasons", response_model=list[LibraryItem])
async def seasons(
    series_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    return await _cached_list(cache, _seasons_key(series_id), TTL.ITEM,
                              lambda: jellyfin.seasons(series_id))


@router.get("/series/{series_id}/seasons/{season_id}/episodes", response_model=list[LibraryItem])
async def episodes(
    series_id: str,
    season_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    return await _cached_list(cache, _episodes_key(series_id, season_id), TTL.ITEM,
                              lambda: jellyfin.episodes(series_id, season_id))


async def _external_scores(imdb_id: str, config, cache, http) -> ExternalScores | None:
    """OMDb scores, cached 7d by IMDB id. Best-effort: a failure returns None
    rather than breaking the detail response."""
    okey = f"omdb:{imdb_id}"
    if (cached := await cache.get_json(okey)) is not None:
        return ExternalScores.model_validate(cached)
    try:
        scores = await OmdbService(config.omdb, http).scores(imdb_id)
    except OmdbError:
        return None
    if scores is not None:
        await cache.set_json(okey, scores.model_dump(), TTL.OMDB)
    return scores


@router.get("/item/{item_id}", response_model=LibraryItem)
async def item(
    item_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
    config: VaultConfig = Depends(get_config),
    http=Depends(get_http),
) -> LibraryItem:
    key = _item_key(item_id)
    if (cached := await cache.get_json(key)) is not None:
        result = LibraryItem.model_validate(cached)
    else:
        try:
            result = await jellyfin.item(item_id)
        except JellyfinError as exc:
            status = exc.status_code if exc.status_code in (404,) else 502
            raise HTTPException(status_code=status, detail=exc.message) from exc
        # Cache the base item (1h); scores are merged at response time with
        # their own 7d TTL, per the caching table in the architecture doc.
        await cache.set_json(key, result.model_dump(), TTL.ITEM)

    if config.omdb.api_key and result.imdb_id:
        result.external_scores = await _external_scores(result.imdb_id, config, cache, http)
    return result


@router.post("/item/{item_id}/progress", status_code=204)
async def report_progress(
    item_id: str,
    update: ProgressUpdate,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> None:
    try:
        await jellyfin.report_progress(item_id, update.position_seconds, update.is_paused)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    # Resume/watched state changed → drop the affected caches.
    await cache.invalidate(_item_key(item_id), _continue_key())
    await cache.invalidate_prefix("lib:movies:")
    await cache.invalidate_prefix("lib:series:")


@router.post("/item/{item_id}/rating", status_code=204)
async def set_rating(
    item_id: str,
    update: RatingUpdate,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> None:
    try:
        await jellyfin.set_rating(item_id, update.rating)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    # user_rating also rides in the cached shelves → drop the same caches as
    # the progress path, not just the item detail.
    await cache.invalidate(_item_key(item_id), _continue_key())
    await cache.invalidate_prefix("lib:movies:")
    await cache.invalidate_prefix("lib:series:")
