"""GET /search?q= — Jellyfin library + TMDB, tagged playable or requestable.

Library hits (already owned) come back as `playable`; TMDB hits that aren't in
the library become `requestable`. Matching is by TMDB id, read from Jellyfin's
ProviderIds. (Download-in-progress state is surfaced by /request/queue.)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_bearer
from config import VaultConfig
from deps import get_config, get_http, get_jellyfin
from models import SearchItem
from services.jellyfin import JellyfinError, JellyfinService
from services.tmdb import TmdbError, TmdbService

router = APIRouter(tags=["search"], dependencies=[Depends(require_bearer)])


@router.get("/search", response_model=list[SearchItem])
async def search(
    q: str = Query(..., min_length=1),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    config: VaultConfig = Depends(get_config),
    http=Depends(get_http),
) -> list[SearchItem]:
    try:
        library = await jellyfin.search(q)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    results: list[SearchItem] = []
    # TMDB movie and TV ids are separate namespaces, so key ownership by
    # (type, tmdb_id) — otherwise an owned movie could hide a same-id TV show.
    owned: set[tuple[str, int]] = set()
    for item in library:
        if item.tmdb_id is not None:
            owned.add((item.type, item.tmdb_id))
        results.append(SearchItem(
            title=item.title, type=item.type, year=item.year, poster_url=item.poster_url,
            source="library", status="playable", library_id=item.id, tmdb_id=item.tmdb_id,
        ))

    # TMDB is optional: without it search still returns library hits.
    if config.tmdb.api_key:
        tmdb = TmdbService(config.tmdb, http)
        try:
            discovered = await tmdb.search_movies(q) + await tmdb.search_series(q)
        except TmdbError as exc:
            raise HTTPException(status_code=502, detail=exc.message) from exc
        for item in discovered:
            if (item.type, item.tmdb_id) in owned:
                continue  # already in the library → shown as playable above
            results.append(SearchItem(
                title=item.title, type=item.type, year=item.year, poster_url=item.poster_url,
                source="discover", status="requestable", tmdb_id=item.tmdb_id,
            ))
    return results
