"""Personal recommendations: M6 shelves plus optional M7 Claude reasons."""
from __future__ import annotations

import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_bearer
from cache import TTL, Cache
from config import VaultConfig
from deps import get_cache, get_config, get_http, get_jellyfin, get_profile_store, get_rating_store, get_tmdb
from models import DiscoverItem, LibraryItem, PickerRequest, PickerResponse, RecommendationResponse
from services.anthropic import AnthropicError, AnthropicService
from services.jellyfin import JellyfinError, JellyfinService
from services.recommender import build_recommendations
from services.tmdb import TmdbError, TmdbService
from services.profile_store import ProfileStore
from services.rating_store import RatingStore

logger = logging.getLogger(__name__)

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


@router.post("/picker", response_model=PickerResponse)
async def picker(
    body: PickerRequest,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    tmdb: TmdbService = Depends(get_tmdb),
    config: VaultConfig = Depends(get_config),
    http: httpx.AsyncClient = Depends(get_http),
    rating_store: RatingStore = Depends(get_rating_store),
    profile_store: ProfileStore = Depends(get_profile_store),
) -> PickerResponse:
    """LLM-curated "Was schauen wir?" picker: one library pick + one discover pick + alternatives."""
    from services.picker import (
        GENRE_NAME_TO_TMDB_ID,
        _genres_to_tmdb_ids,
        build_fallback_response,
        build_picker_response_from_llm,
        gather_discover_candidates,
        gather_library_candidates,
    )
    from services.recommender import _snapshot_index, _item_key

    # ── Gather profiles ──────────────────────────────────────────────────────
    janno = profile_store.get("janno")
    tanno = profile_store.get("tanno")
    active_profiles = (
        [janno] if body.profile == "janno"
        else [tanno] if body.profile == "tanno"
        else [janno, tanno]
    )
    profiles_summary = "; ".join(
        f"{p.person}: Lieblingsgenres={p.favorite_genres or ['unbekannt']}, Grusel-Komfort={p.fear_comfort}/10"
        for p in active_profiles
    )
    # For surprise mode, add profile genres to the request genres
    effective_genres = body.genres
    if body.surprise:
        profile_genres: list[str] = []
        for p in active_profiles:
            profile_genres.extend(p.favorite_genres)
        effective_genres = list(dict.fromkeys(profile_genres))[:5]  # dedupe, cap

    request_summary = (
        f"Wer schaut: {body.profile}; "
        f"Genres: {body.genres or ['beliebig']}; "
        f"Gruselintensität: {body.mood_fear if body.mood_fear is not None else 'egal'}/10; "
        f"Länge: {body.length or 'egal'}; "
        f"Überraschung: {body.surprise}"
    )

    # ── Gather library candidates ────────────────────────────────────────────
    snapshots = rating_store.list()
    snapshot_idx = _snapshot_index(snapshots)
    # Build a simple by-id index for the picker
    snapshots_by_id: dict = {s.item_id: s for s in snapshots}
    if body.length == "series":
        include_types = ["Series"]
    else:
        include_types = ["Movie"] if body.length in ("short", "feature") else ["Movie", "Series"]

    library_items: list[LibraryItem] = []
    for itype in include_types:
        try:
            genre_filter = effective_genres if effective_genres else None
            fetched = await jellyfin.shelf(
                include_type=itype,
                sort="top_rated",
                genres=genre_filter,
                unplayed=False,
                limit=35,
            )
            library_items.extend(fetched)
        except JellyfinError as exc:
            logger.warning("Jellyfin shelf error for %s: %s", itype, exc)

    # Dedupe
    seen_lib: set[str] = set()
    deduped_lib: list[LibraryItem] = []
    for item in library_items:
        if item.id not in seen_lib:
            deduped_lib.append(item)
            seen_lib.add(item.id)

    lib_candidates = gather_library_candidates(deduped_lib, body, snapshots_by_id, limit=30)

    # ── Gather discover candidates ───────────────────────────────────────────
    owned_tmdb = {(item.type, item.tmdb_id) for item in deduped_lib if item.tmdb_id is not None}
    genre_ids = _genres_to_tmdb_ids(effective_genres) if effective_genres else []

    discover_items: list[DiscoverItem] = []
    try:
        if genre_ids:
            if body.length != "series":
                discover_items.extend(await tmdb.discover_movies_by_genres(genre_ids))
            if body.length in (None, "series"):
                discover_items.extend(await tmdb.discover_series_by_genres(genre_ids))
        else:
            # No genre filter — use popular/trending
            if body.length != "series":
                discover_items.extend(await tmdb.discover_movies())
                discover_items.extend(await tmdb.trending_movies())
            if body.length in (None, "series"):
                discover_items.extend(await tmdb.discover_series())
                discover_items.extend(await tmdb.trending_series())
    except TmdbError as exc:
        logger.warning("TMDB error during picker candidate gathering: %s", exc)

    # Dedupe discover
    seen_disc: set[tuple[str, int]] = set()
    deduped_disc: list[DiscoverItem] = []
    for item in discover_items:
        key = (item.type, item.tmdb_id)
        if key not in seen_disc:
            deduped_disc.append(item)
            seen_disc.add(key)

    disc_candidates = gather_discover_candidates(deduped_disc, owned_tmdb, body, limit=30)

    # ── Index candidates by id for fast lookup ────────────────────────────────
    lib_by_id = {c["id"]: c for c in lib_candidates}
    disc_by_id = {c["id"]: c for c in disc_candidates}

    # ── LLM curation ────────────────────────────────────────────────────────
    llm_used = False
    if config.anthropic.api_key and (lib_candidates or disc_candidates):
        anthropic = AnthropicService(config.anthropic, http)
        try:
            llm_result = await anthropic.curate_picks(
                request_summary=request_summary,
                profiles_summary=profiles_summary,
                library_candidates=lib_candidates,
                discover_candidates=disc_candidates,
            )
            library_pick, discover_pick, alternatives = build_picker_response_from_llm(
                llm_result, lib_by_id, disc_by_id
            )
            llm_used = True
        except AnthropicError as exc:
            logger.warning("Anthropic picker curation failed, using fallback: %s", exc)
            library_pick, discover_pick, alternatives = build_fallback_response(
                lib_candidates, disc_candidates
            )
    else:
        library_pick, discover_pick, alternatives = build_fallback_response(
            lib_candidates, disc_candidates
        )

    return PickerResponse(
        library_pick=library_pick,
        discover_pick=discover_pick,
        alternatives=alternatives,
        llm_used=llm_used,
    )

