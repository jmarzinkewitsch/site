from __future__ import annotations

import hmac
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from auth import require_bearer, require_bearer_or_kiosk
from cache import Cache
from config import ConfigStore, VaultConfig
from deps import get_cache, get_config, get_http, get_jellyfin, get_store
from models import KioskMediaItem, KioskMediaOverview, LibraryItem, TrailerStreamInfo
from routers.library import _resolve_trailer_stream, _trailer_stream_key, _trailer_url
from services.kiosk_curation import curate_kiosk_overview
from services.jellyfin import JellyfinError, JellyfinService

router = APIRouter(tags=["kiosk"])
_KIOSK_DIR = Path(__file__).resolve().parent.parent / "web" / "kiosk"

# The kiosk runs 24/7 in a Chromium that aggressively caches static assets — so a
# deployed UI change would never show up. Force revalidation on every load; on the
# LAN this is cheap (304s) and guarantees the panel always serves the latest UI.
_NO_CACHE = {"Cache-Control": "no-cache"}


def _token_matches(config: VaultConfig, token: str | None) -> bool:
    if not token:
        return False
    if config.bearer_token and hmac.compare_digest(token, config.bearer_token):
        return True
    if config.kiosk_token and hmac.compare_digest(token, config.kiosk_token):
        return True
    return False


@router.get("/kiosk", response_class=FileResponse)
async def kiosk_app() -> FileResponse:
    return FileResponse(_KIOSK_DIR / "index.html", headers=_NO_CACHE)


@router.get("/kiosk/app.css", response_class=FileResponse)
async def kiosk_css() -> FileResponse:
    return FileResponse(_KIOSK_DIR / "app.css", media_type="text/css", headers=_NO_CACHE)


@router.get("/kiosk/app.js", response_class=FileResponse)
async def kiosk_js() -> FileResponse:
    return FileResponse(_KIOSK_DIR / "app.js", media_type="text/javascript", headers=_NO_CACHE)


@router.get("/kiosk/manifest.json", response_class=FileResponse)
async def kiosk_manifest() -> FileResponse:
    return FileResponse(_KIOSK_DIR / "manifest.json", media_type="application/manifest+json")


@router.get("/kiosk/status", dependencies=[Depends(require_bearer)])
async def kiosk_status() -> dict:
    return {"ok": True, "mode": "kiosk", "realtime": "/realtime"}


@router.post("/kiosk/session")
async def kiosk_session(
    request: Request,
    store: ConfigStore = Depends(get_store),
) -> dict:
    config = store.get()
    client_ip = request.client.host if request.client else ""
    if client_ip not in config.kiosk_device.allowed_ips:
        raise HTTPException(status_code=403, detail="Dieses Gerät ist nicht als Kiosk freigegeben")
    token = store.ensure_kiosk_token()
    return {"token": token}


def _media_subtitle(item: LibraryItem) -> str | None:
    if item.type == "Episode":
        bits = [item.series_name, item.episode_code]
        return " · ".join(bit for bit in bits if bit)
    bits = [str(item.year) if item.year else None, ", ".join(item.genres[:2]) if item.genres else None]
    return " · ".join(bit for bit in bits if bit)


def _media_item(item: LibraryItem) -> KioskMediaItem:
    return KioskMediaItem(
        id=item.id,
        type=item.type,
        title=item.title,
        subtitle=_media_subtitle(item),
        overview=item.overview,
        # Point image URLs at vault-api's proxy so the browser never needs to reach
        # Jellyfin's internal docker host or hold its key. Keep None when absent.
        poster_url=f"/kiosk/media/image/{item.id}?kind=primary" if item.poster_url else None,
        backdrop_url=f"/kiosk/media/image/{item.id}?kind=backdrop" if item.backdrop_url else None,
        progress=item.played_percentage,
        runtime_seconds=item.runtime_seconds,
        playable=item.type in {"Movie", "Episode"},
    )


@router.get(
    "/kiosk/media/overview",
    response_model=KioskMediaOverview,
    dependencies=[Depends(require_bearer_or_kiosk)],
)
async def kiosk_media_overview(jellyfin: JellyfinService = Depends(get_jellyfin)) -> KioskMediaOverview:
    try:
        continue_watching = await jellyfin.continue_watching(limit=8)
        next_up = await jellyfin.next_up(limit=8)
        latest_movies = await jellyfin.latest("Movie", 8)
        latest_series = await jellyfin.latest("Series", 8)
        spotlight = await jellyfin.shelf(include_type="Movie", sort="random", unplayed=False, limit=12)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    curated = curate_kiosk_overview(
        continue_watching=continue_watching,
        next_up=next_up,
        latest_movies=latest_movies,
        latest_series=latest_series,
        spotlight=spotlight,
    )
    return KioskMediaOverview(
        continue_watching=[_media_item(item) for item in curated["continue_watching"]],
        next_up=[_media_item(item) for item in curated["next_up"]],
        latest_movies=[_media_item(item) for item in curated["latest_movies"]],
        latest_series=[_media_item(item) for item in curated["latest_series"]],
        spotlight=[_media_item(item) for item in curated["spotlight"]],
    )


@router.get(
    "/kiosk/media/item/{item_id}",
    response_model=KioskMediaItem,
    dependencies=[Depends(require_bearer_or_kiosk)],
)
async def kiosk_media_item(
    item_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
) -> KioskMediaItem:
    try:
        item = await jellyfin.item(item_id)
    except JellyfinError as exc:
        raise HTTPException(status_code=404 if exc.status_code == 404 else 502, detail=exc.message) from exc
    result = _media_item(item)
    if item.type in {"Movie", "Episode"}:
        try:
            stream = await jellyfin.stream(item_id)
        except JellyfinError:
            return result
        # Hand the browser vault-api's stream proxy, not the raw Jellyfin URL with
        # the embedded api_key — the proxy forwards Range and keeps the key inside.
        result.stream_url = f"/kiosk/media/stream/{item_id}"
        result.runtime_seconds = stream.runtime_seconds or result.runtime_seconds
        result.playable = True
    return result


@router.get("/kiosk/media/image/{item_id}", dependencies=[Depends(require_bearer_or_kiosk)])
async def kiosk_media_image(
    item_id: str,
    kind: str = "primary",
    jellyfin: JellyfinService = Depends(get_jellyfin),
) -> Response:
    image_type = "Backdrop" if kind == "backdrop" else "Primary"
    max_width = 1920 if kind == "backdrop" else 600
    try:
        upstream = await jellyfin.image_response(item_id, image_type, max_width=max_width)
    except JellyfinError as exc:
        raise HTTPException(status_code=404 if exc.status_code == 404 else 502, detail=exc.message) from exc
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/kiosk/media/stream/{item_id}", dependencies=[Depends(require_bearer_or_kiosk)])
async def kiosk_media_stream(
    item_id: str,
    request: Request,
    jellyfin: JellyfinService = Depends(get_jellyfin),
) -> StreamingResponse:
    try:
        upstream = await jellyfin.stream_proxy(item_id, range_header=request.headers.get("range"))
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    passthrough = {
        key: upstream.headers[key]
        for key in ("content-type", "content-length", "content-range", "accept-ranges")
        if key in upstream.headers
    }
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=passthrough,
        background=BackgroundTask(upstream.aclose),
    )


@router.get(
    "/kiosk/media/item/{item_id}/trailer",
    response_model=TrailerStreamInfo,
    dependencies=[Depends(require_bearer_or_kiosk)],
)
async def kiosk_media_trailer(
    item_id: str,
    jellyfin: JellyfinService = Depends(get_jellyfin),
    cache: Cache = Depends(get_cache),
    config: VaultConfig = Depends(get_config),
    http: httpx.AsyncClient = Depends(get_http),
) -> TrailerStreamInfo:
    """Browser-playable trailer (MP4 CDN URL) for the kiosk. Mirrors
    /library/item/{id}/trailer-stream but accepts the kiosk token, and shares
    its cache key so both clients hit the same resolved trailer."""
    key = _trailer_stream_key(item_id)
    if (cached := await cache.get_json(key)) is not None:
        return TrailerStreamInfo.model_validate(cached)
    try:
        result = await jellyfin.item(item_id)
    except JellyfinError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="trailer not available") from exc
        raise HTTPException(status_code=502, detail=exc.message) from exc

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


@router.websocket("/realtime")
async def realtime_socket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    config: VaultConfig = websocket.app.state.config_store.get()
    if not _token_matches(config, token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await websocket.send_json({"type": "hello", "source": "vault-api", "features": []})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        return
