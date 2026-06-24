from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from auth import require_bearer_or_kiosk
from deps import get_roon
from models import (
    MusicAlbum,
    MusicAlbumShelf,
    MusicNowPlaying,
    MusicOutput,
    MusicGroupRequest,
    MusicPlayRequest,
    MusicSearchResult,
    MusicSearchShelf,
    MusicStatus,
    MusicTransportUpdate,
    MusicZone,
)
from services.roon import RoonError, RoonService

router = APIRouter(prefix="/music", tags=["music"], dependencies=[Depends(require_bearer_or_kiosk)])


def _roon_error(exc: RoonError) -> HTTPException:
    status = exc.status_code if exc.status_code in {400, 404, 503} else 502
    return HTTPException(status_code=status, detail=exc.message)


def _image_url(image_key: str | None, size: int = 500) -> str | None:
    if not image_key:
        return None
    return f"/music/image/{image_key}?width={size}&height={size}"


def _now_playing(raw: dict | None) -> MusicNowPlaying | None:
    if not raw:
        return None
    image_key = raw.get("image_key")
    return MusicNowPlaying(
        title=raw.get("title"),
        subtitle=raw.get("subtitle"),
        image_key=image_key,
        image_url=_image_url(image_key, 900),
        seek_position=raw.get("seek_position"),
        length=raw.get("length"),
    )


def _zone(raw: dict) -> MusicZone:
    outputs = [
        MusicOutput(
            id=output.get("output_id") or output.get("id") or "",
            name=output.get("display_name") or output.get("name") or "Output",
            volume=(output.get("volume") or {}).get("value") if isinstance(output.get("volume"), dict) else output.get("volume"),
            can_group_with_output_ids=list(output.get("can_group_with_output_ids") or []),
        )
        for output in raw.get("outputs", [])
    ]
    return MusicZone(
        id=raw.get("zone_id") or raw.get("id") or "",
        name=raw.get("display_name") or raw.get("name") or "Zone",
        state=raw.get("state") or "unknown",
        now_playing=_now_playing(raw.get("now_playing")),
        outputs=outputs,
    )


def _album(raw: dict) -> MusicAlbum:
    image_key = raw.get("image_key")
    return MusicAlbum(
        item_key=raw.get("item_key") or "",
        album_index=raw.get("album_index"),
        title=raw.get("title") or "Unbenannt",
        subtitle=raw.get("subtitle"),
        image_key=image_key,
        image_url=_image_url(image_key, 500),
        is_playable=bool(raw.get("is_playable")),
    )


def _search_result(raw: dict) -> MusicSearchResult:
    image_key = raw.get("image_key")
    return MusicSearchResult(
        item_key=raw.get("item_key") or "",
        title=raw.get("title") or "Unbenannt",
        subtitle=raw.get("subtitle"),
        image_key=image_key,
        image_url=_image_url(image_key, 500),
        hint=raw.get("hint"),
        parent_title=raw.get("parent_title"),
        hierarchy=raw.get("hierarchy"),
        browser_session_key=raw.get("browser_session_key"),
        album_index=raw.get("album_index"),
        is_playable=bool(raw.get("is_playable") or raw.get("item_key")),
    )


@router.get("/status", response_model=MusicStatus)
async def status(roon: RoonService = Depends(get_roon)) -> MusicStatus:
    try:
        raw = await roon.get_json("status")
    except RoonError as exc:
        raise _roon_error(exc) from exc
    return MusicStatus(
        connected=bool(raw.get("connected")),
        core_name=raw.get("core_name"),
        zone_count=int(raw.get("zone_count") or 0),
    )


@router.get("/zones", response_model=list[MusicZone])
async def zones(roon: RoonService = Depends(get_roon)) -> list[MusicZone]:
    try:
        raw = await roon.get_json("zones")
    except RoonError as exc:
        raise _roon_error(exc) from exc
    return [_zone(zone) for zone in raw.get("zones", [])]


@router.get("/albums", response_model=MusicAlbumShelf)
async def albums(
    query: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    roon: RoonService = Depends(get_roon),
) -> MusicAlbumShelf:
    try:
        raw = await roon.get_json(
            "albums",
            params={"query": query, "offset": str(offset), "limit": str(limit)},
        )
    except RoonError as exc:
        raise _roon_error(exc) from exc
    return MusicAlbumShelf(
        albums=[_album(album) for album in raw.get("albums", [])],
        total=int(raw.get("total") or 0),
        offset=int(raw.get("offset") or offset),
        limit=int(raw.get("limit") or limit),
        query=raw.get("query") or query,
    )


@router.get("/search", response_model=MusicSearchShelf)
async def search(
    query: str = Query(..., min_length=1, max_length=100),
    source: str = Query("roon", pattern="^(roon|albums)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    roon: RoonService = Depends(get_roon),
) -> MusicSearchShelf:
    try:
        raw = await roon.get_json(
            "search",
            params={"query": query, "source": source, "offset": str(offset), "limit": str(limit)},
        )
    except RoonError as exc:
        raise _roon_error(exc) from exc
    return MusicSearchShelf(
        source=raw.get("source") or source,
        fallback_from=raw.get("fallback_from"),
        title=raw.get("title"),
        subtitle=raw.get("subtitle"),
        query=raw.get("query") or query,
        results=[_search_result(item) for item in raw.get("results", [])],
        total=int(raw.get("total") or 0),
        offset=int(raw.get("offset") or offset),
        limit=int(raw.get("limit") or limit),
        expanded=bool(raw.get("expanded")),
    )


@router.post("/transport", status_code=204)
async def transport(
    body: MusicTransportUpdate,
    roon: RoonService = Depends(get_roon),
) -> None:
    payload = {"zoneId": body.zone_id, "action": body.action}
    if body.output_id is not None:
        payload["outputId"] = body.output_id
    if body.volume is not None:
        payload["volume"] = body.volume
    try:
        await roon.post_json("transport", json=payload)
    except RoonError as exc:
        raise _roon_error(exc) from exc


@router.post("/group", status_code=204)
async def group(
    body: MusicGroupRequest,
    roon: RoonService = Depends(get_roon),
) -> None:
    if len(body.output_ids) < 2:
        raise HTTPException(status_code=422, detail="Mindestens zwei Outputs erforderlich")
    try:
        await roon.post_json("group", json={"outputIds": body.output_ids})
    except RoonError as exc:
        raise _roon_error(exc) from exc


@router.post("/ungroup", status_code=204)
async def ungroup(
    body: MusicGroupRequest,
    roon: RoonService = Depends(get_roon),
) -> None:
    if not body.output_ids:
        raise HTTPException(status_code=422, detail="Mindestens ein Output erforderlich")
    try:
        await roon.post_json("ungroup", json={"outputIds": body.output_ids})
    except RoonError as exc:
        raise _roon_error(exc) from exc


@router.post("/play", status_code=204)
async def play(
    body: MusicPlayRequest,
    roon: RoonService = Depends(get_roon),
) -> None:
    payload: dict = {"zoneId": body.zone_id}
    if body.item_key is not None:
        payload["itemKey"] = body.item_key
    if body.album_index is not None:
        payload["albumIndex"] = body.album_index
    if body.hierarchy is not None:
        payload["hierarchy"] = body.hierarchy
    if body.browser_session_key is not None:
        payload["browserSessionKey"] = body.browser_session_key
    try:
        await roon.post_json("play", json=payload)
    except RoonError as exc:
        raise _roon_error(exc) from exc


@router.get("/image/{image_key}")
async def image(
    image_key: str,
    width: int = Query(500, ge=50, le=1200),
    height: int = Query(500, ge=50, le=1200),
    roon: RoonService = Depends(get_roon),
) -> Response:
    try:
        proxied = await roon.image(image_key, width=width, height=height)
    except RoonError as exc:
        raise _roon_error(exc) from exc
    return Response(
        content=proxied.content,
        status_code=proxied.status_code,
        media_type=proxied.media_type,
    )
