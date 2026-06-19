"""Library endpoints — the read path the app's browse UI hits.

Reads are cached (Redis) with the TTLs from the architecture doc; a progress
write invalidates the affected caches so watched/resume state doesn't go stale.
"""
from __future__ import annotations

import asyncio

import httpx
try:
    import yt_dlp
except ImportError:  # pragma: no cover - runtime dependency installed in production image
    from types import SimpleNamespace
    yt_dlp = SimpleNamespace(YoutubeDL=None)
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_bearer
from cache import TTL, Cache
from config import VaultConfig
from deps import get_cache, get_config, get_http, get_jellyfin
from models import ExternalScores, LibraryItem, ProgressUpdate, RatingUpdate, RemoteSubtitleInfo, SubtitleDownloadBody, SubtitleTrackInfo, TrailerStreamInfo, WatchedUpdate
from services.jellyfin import JellyfinError, JellyfinService
from services.omdb import OmdbError, OmdbService
from services.tmdb import TmdbError, TmdbService

router = APIRouter(prefix="/library", tags=["library"], dependencies=[Depends(require_bearer)])


def _continue_key() -> str:
    return "lib:continue"


def _next_up_key(limit: int) -> str:
    return f"lib:nextup:{limit}"


def _list_key(kind: str, start: int, limit: int) -> str:
    return f"lib:{kind}:{start}:{limit}"


def _item_key(item_id: str) -> str:
    return f"lib:item:{item_id}"



def _trailer_stream_key(item_id: str) -> str:
    return f"trailer:stream:{item_id}"


def _pick_trailer_format(info: dict) -> tuple[str, str | None] | None:
    """Pick an AVPlayer-friendly trailer stream from yt-dlp metadata.

    Prefer progressive H.264/AAC MP4 (YouTube itag 18/22) because the Apple TV
    can open it directly. Fall back to HLS when yt-dlp exposes a native m3u8.
    """
    formats = info.get("formats") or []
    preferred_itags = {"22", "18"}
    for fmt in formats:
        if str(fmt.get("format_id")) in preferred_itags and fmt.get("url"):
            return fmt["url"], "mp4"
    for fmt in formats:
        if (fmt.get("ext") == "mp4" and fmt.get("vcodec", "none") != "none"
                and fmt.get("acodec", "none") != "none" and fmt.get("url")):
            return fmt["url"], "mp4"
    for fmt in formats:
        protocol = str(fmt.get("protocol") or "")
        if fmt.get("url") and ("m3u8" in protocol or fmt.get("ext") == "m3u8"):
            return fmt["url"], "hls"
    if info.get("url"):
        return info["url"], info.get("ext")
    return None


def _resolve_trailer_stream_sync(url: str) -> TrailerStreamInfo | None:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "22/18/best[ext=mp4][vcodec!=none][acodec!=none]/best",
    }
    if yt_dlp.YoutubeDL is None:
        return None
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        return None
    picked = _pick_trailer_format(info)
    if picked is None:
        return None
    return TrailerStreamInfo(url=picked[0], container=picked[1])


async def _resolve_trailer_stream(url: str) -> TrailerStreamInfo | None:
    try:
        return await asyncio.to_thread(_resolve_trailer_stream_sync, url)
    except Exception:
        return None

def _latest_key(kind: str, limit: int) -> str:
    return f"lib:latest:{kind}:{limit}"


def _seasons_key(series_id: str) -> str:
    return f"lib:series:{series_id}:seasons"


def _episodes_key(series_id: str, season_id: str) -> str:
    return f"lib:series:{series_id}:season:{season_id}:episodes"


def _jellyfin_http_error(exc: JellyfinError) -> HTTPException:
    """Map an upstream Jellyfin failure to an HTTP status the app can act on.

    Only 404 (not found) is forwarded — it is unambiguous and the client handles
    it directly. Upstream auth failures (401/403) are deliberately NOT forwarded:
    the tvOS app reserves 401 for an invalid *vault* bearer token (VaultClient
    .validateBearer probes an app-facing route and treats any 401 as a bad app
    token), so a bad/expired Jellyfin credential must surface as an upstream
    error (502 Bad Gateway), not as a bad app token. Everything else is 502 too.
    """
    status = exc.status_code if exc.status_code == 404 else 502
    return HTTPException(status_code=status, detail=exc.message)


async def _cached_list(cache, key, ttl, fetch) -> list[LibraryItem]:
    if (cached := await cache.get_json(key)) is not None:
        return [LibraryItem.model_validate(row) for row in cached]
    try:
        items = await fetch()
    except JellyfinError as exc:
        raise _jellyfin_http_error(exc) from exc
    await cache.set_json(key, [i.model_dump() for i in items], ttl)
    return items


async def _invalidate_playback_caches(cache: Cache, item_id: str) -> None:
    """Drop cached shelves/details that carry watched/resume state."""
    await cache.invalidate(_item_key(item_id), _continue_key(), "lib:nextup")
    await cache.invalidate_prefix("lib:movies:")
    await cache.invalidate_prefix("lib:series:")
    await cache.invalidate_prefix("lib:latest:")
    await cache.invalidate_prefix("lib:nextup:")
    await cache.invalidate_prefix("recommend:")


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


@router.get("/latest", response_model=list[LibraryItem])
async def latest(
    type: str = Query("Movie"),
    limit: int = Query(16, ge=1, le=100),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    # Recently added shelf — ordered by date added, not SortName.
    include = "Series" if type.lower() == "series" else "Movie"
    return await _cached_list(cache, _latest_key(include, limit), TTL.LIBRARY,
                              lambda: jellyfin.latest(include, limit))


@router.get("/continue", response_model=list[LibraryItem])
async def continue_watching(
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    # Short TTL: resume positions move while the user watches.
    return await _cached_list(cache, _continue_key(), 30,
                              lambda: jellyfin.continue_watching())


@router.get("/nextup", response_model=list[LibraryItem])
async def next_up(
    limit: int = Query(24, ge=1, le=100),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[LibraryItem]:
    # Short TTL: next-up can change as soon as playback progress is reported.
    return await _cached_list(cache, _next_up_key(limit), 30,
                              lambda: jellyfin.next_up(limit))


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


async def _trailer_url(media_type: str, tmdb_id: int, config, cache, http) -> str | None:
    """TMDB YouTube trailer URL, cached 7d by media type and TMDB id.

    Best-effort like OMDb enrichment: TMDB failures must not break playback
    metadata for the owned item.
    """
    tkey = f"tmdb:trailer:{media_type}:{tmdb_id}"
    if (cached := await cache.get_json(tkey)) is not None:
        return cached.get("url")
    try:
        url = await TmdbService(config.tmdb, http).trailer_url(media_type, tmdb_id)
    except TmdbError:
        return None
    await cache.set_json(tkey, {"url": url}, TTL.TMDB)
    return url


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


@router.get("/item/{item_id}/next-episode", response_model=LibraryItem | None)
async def next_episode(
    item_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> LibraryItem | None:
    try:
        current = await jellyfin.item(item_id)
    except JellyfinError as exc:
        raise _jellyfin_http_error(exc) from exc

    if current.type != "Episode" or not current.series_id or not current.season_id:
        return None

    seasons = await _cached_list(cache, _seasons_key(current.series_id), TTL.ITEM,
                                 lambda: jellyfin.seasons(current.series_id))
    seasons = sorted(seasons, key=lambda season: (season.index_number is None, season.index_number or 0, season.title))

    async def sorted_episodes(season_id: str) -> list[LibraryItem]:
        episodes = await _cached_list(cache, _episodes_key(current.series_id, season_id), TTL.ITEM,
                                      lambda: jellyfin.episodes(current.series_id, season_id))
        return sorted(episodes, key=lambda episode: (episode.index_number is None, episode.index_number or 0, episode.title))

    current_episodes = await sorted_episodes(current.season_id)
    for episode in current_episodes:
        if episode.id == current.id:
            continue
        if current.index_number is not None and episode.index_number is not None:
            if episode.index_number > current.index_number:
                return episode
        elif episode.id > current.id:
            return episode

    current_season_index = next((idx for idx, season in enumerate(seasons) if season.id == current.season_id), None)
    if current_season_index is None:
        return None

    for season in seasons[current_season_index + 1:]:
        episodes = await sorted_episodes(season.id)
        if episodes:
            return episodes[0]
    return None



@router.get("/item/{item_id}/trailer-stream", response_model=TrailerStreamInfo)
async def trailer_stream(
    item_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
    config: VaultConfig = Depends(get_config),
    http: httpx.AsyncClient = Depends(get_http),
) -> TrailerStreamInfo:
    key = _trailer_stream_key(item_id)
    if (cached := await cache.get_json(key)) is not None:
        return TrailerStreamInfo.model_validate(cached)

    try:
        result = await jellyfin.item(item_id)
    except JellyfinError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="trailer not available") from exc
        raise _jellyfin_http_error(exc) from exc

    trailer_url = result.trailer_url
    if trailer_url is None and config.tmdb.api_key and result.tmdb_id and result.type in {"Movie", "Series"}:
        trailer_url = await _trailer_url(result.type, result.tmdb_id, config, cache, http)
    if trailer_url is None:
        raise HTTPException(status_code=404, detail="trailer not available")

    stream = await _resolve_trailer_stream(trailer_url)
    if stream is None:
        raise HTTPException(status_code=404, detail="trailer not available")
    await cache.set_json(key, stream.model_dump(), 60 * 60)
    return stream

@router.get("/item/{item_id}", response_model=LibraryItem)
async def item(
    item_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
    config: VaultConfig = Depends(get_config),
    http: httpx.AsyncClient = Depends(get_http),
) -> LibraryItem:
    key = _item_key(item_id)
    if (cached := await cache.get_json(key)) is not None:
        result = LibraryItem.model_validate(cached)
    else:
        try:
            result = await jellyfin.item(item_id)
        except JellyfinError as exc:
            raise _jellyfin_http_error(exc) from exc
        # Cache the base item (1h); scores are merged at response time with
        # their own 7d TTL, per the caching table in the architecture doc.
        await cache.set_json(key, result.model_dump(), TTL.ITEM)

    if config.omdb.api_key and result.imdb_id:
        result.external_scores = await _external_scores(result.imdb_id, config, cache, http)
    if config.tmdb.api_key and result.tmdb_id and result.type in {"Movie", "Series"}:
        result.trailer_url = await _trailer_url(result.type, result.tmdb_id, config, cache, http)
    return result


@router.post("/item/{item_id}/progress", status_code=204)
async def report_progress(
    item_id: str,
    update: ProgressUpdate,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> None:
    try:
        await jellyfin.report_progress(
            item_id,
            update.position_seconds,
            update.is_paused,
            update.media_source_id,
        )
    except JellyfinError as exc:
        raise _jellyfin_http_error(exc) from exc
    # Resume/watched state changed → drop affected shelves/details, including
    # recommendations that score on played/played_percentage.
    await _invalidate_playback_caches(cache, item_id)


@router.post("/item/{item_id}/watched", status_code=204)
async def set_watched(
    item_id: str,
    update: WatchedUpdate,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> None:
    try:
        if update.watched:
            await jellyfin.mark_played(item_id)
        else:
            await jellyfin.mark_unplayed(item_id)
    except JellyfinError as exc:
        raise _jellyfin_http_error(exc) from exc
    await _invalidate_playback_caches(cache, item_id)


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
        raise _jellyfin_http_error(exc) from exc
    # user_rating also rides in the cached shelves and feeds the recommendation
    # taste profile → drop the same caches as the progress path, plus recs.
    await cache.invalidate(_item_key(item_id), _continue_key())
    await cache.invalidate_prefix("lib:nextup:")
    await cache.invalidate_prefix("lib:movies:")
    await cache.invalidate_prefix("lib:series:")
    await cache.invalidate_prefix("recommend:")


@router.get("/item/{item_id}/subtitles/search", response_model=list[RemoteSubtitleInfo])
async def search_subtitles(
    item_id: str,
    languages: str = Query("ger,eng", description="Comma-separated ISO-639-2 language codes"),
    jellyfin: JellyfinService = Depends(get_jellyfin),
) -> list[RemoteSubtitleInfo]:
    """Search for remote subtitles via Jellyfin's OpenSubtitles plugin.

    Returns results merged across all requested languages, hash-matches first,
    then sorted by download count descending.
    """
    lang_list = [l.strip() for l in languages.split(",")]
    try:
        return await jellyfin.search_subtitles(item_id, lang_list)
    except JellyfinError as exc:
        raise _jellyfin_http_error(exc) from exc


@router.post("/item/{item_id}/subtitles/download", response_model=list[SubtitleTrackInfo])
async def download_subtitle(
    item_id: str,
    body: SubtitleDownloadBody,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
) -> list[SubtitleTrackInfo]:
    """Download a remote subtitle and attach it to the item as an external sidecar.

    Returns the refreshed subtitle track list so the client can immediately
    update the player without an extra round-trip. Invalidates playback caches
    so the next stream fetch sees the new track.
    """
    try:
        tracks = await jellyfin.download_subtitle(item_id, body.subtitle_id)
    except JellyfinError as exc:
        raise _jellyfin_http_error(exc) from exc
    await _invalidate_playback_caches(cache, item_id)
    return tracks
