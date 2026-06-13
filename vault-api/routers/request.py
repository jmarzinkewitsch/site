"""Request endpoints — add titles to Radarr/Sonarr and read the download queue.

Movie: tmdbId straight to Radarr. Series: TMDB external_ids → tvdbId → Sonarr.
The queue combines both *arr instances and is cached briefly (it must stay fresh).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import require_bearer
from cache import TTL, Cache
from config import VaultConfig
from deps import get_cache, get_config, get_http, get_radarr, get_sonarr, get_tmdb
from models import QueueItem, RequestMovieBody, RequestResult, RequestSeriesBody
from services.arr import ArrError
from services.radarr import RadarrService
from services.sonarr import SonarrService
from services.tmdb import TmdbError, TmdbService

router = APIRouter(prefix="/request", tags=["request"], dependencies=[Depends(require_bearer)])

_QUEUE_KEY = "request:queue"


@router.post("/movie", response_model=RequestResult)
async def request_movie(
    body: RequestMovieBody,
    radarr: RadarrService = Depends(get_radarr),
    config: VaultConfig = Depends(get_config),
    cache: Cache = Depends(get_cache),
) -> RequestResult:
    try:
        result = await radarr.add(
            body.tmdb_id, body.quality_profile_id, body.root_folder,
            default_profile=config.radarr_defaults.quality_profile_id,
            default_root=config.radarr_defaults.root_folder,
        )
    except ArrError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message) from exc
    await cache.invalidate(_QUEUE_KEY)
    return result


@router.post("/series", response_model=RequestResult)
async def request_series(
    body: RequestSeriesBody,
    sonarr: SonarrService = Depends(get_sonarr),
    tmdb: TmdbService = Depends(get_tmdb),
    config: VaultConfig = Depends(get_config),
    cache: Cache = Depends(get_cache),
) -> RequestResult:
    try:
        tvdb_id = await tmdb.series_tvdb_id(body.tmdb_id)
    except TmdbError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    if tvdb_id is None:
        raise HTTPException(status_code=422, detail="Keine tvdbId für diese Serie (Sonarr braucht sie)")
    try:
        result = await sonarr.add(
            tvdb_id, body.quality_profile_id, body.root_folder,
            default_profile=config.sonarr_defaults.quality_profile_id,
            default_root=config.sonarr_defaults.root_folder,
        )
    except ArrError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message) from exc
    await cache.invalidate(_QUEUE_KEY)
    return result


@router.get("/queue", response_model=list[QueueItem])
async def request_queue(
    config: VaultConfig = Depends(get_config),
    cache: Cache = Depends(get_cache),
    http=Depends(get_http),
) -> list[QueueItem]:
    if (cached := await cache.get_json(_QUEUE_KEY)) is not None:
        return [QueueItem.model_validate(row) for row in cached]

    # Combine whichever *arr instances are configured, independently: a missing
    # OR temporarily unreachable service only hides its own queue, never the
    # other's. /health surfaces which service is down.
    items: list[QueueItem] = []
    complete = True
    if config.radarr.configured:
        try:
            items += await RadarrService(config.radarr.base_url, config.radarr.api_key, http).queue()
        except ArrError:
            complete = False
    if config.sonarr.configured:
        try:
            items += await SonarrService(config.sonarr.base_url, config.sonarr.api_key, http).queue()
        except ArrError:
            complete = False

    # Only cache a complete result so a recovered service reappears promptly
    # instead of being hidden for the cache TTL.
    if complete:
        await cache.set_json(_QUEUE_KEY, [i.model_dump() for i in items], TTL.ARR_QUEUE)
    return items
