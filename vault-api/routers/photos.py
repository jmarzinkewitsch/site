from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from auth import require_bearer_or_kiosk
from config import VaultConfig
from deps import get_config, get_http
from models import PhotoOverview
from services.immich import ImmichError, ImmichService

router = APIRouter(prefix="/photos", tags=["photos"], dependencies=[Depends(require_bearer_or_kiosk)])


def _immich_error(exc: ImmichError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/overview", response_model=PhotoOverview)
async def overview(
    config: VaultConfig = Depends(get_config),
    http=Depends(get_http),
) -> PhotoOverview:
    if not config.immich.configured:
        return PhotoOverview()
    svc = ImmichService(config.immich, http)
    try:
        photos = (
            await svc.album_assets(config.kiosk_photos.album_id, count=config.kiosk_photos.count)
            if config.kiosk_photos.album_id
            else await svc.random_assets(count=config.kiosk_photos.count)
        )
    except ImmichError as exc:
        raise _immich_error(exc) from exc
    return PhotoOverview(photos=photos)


@router.get("/image/{asset_id}")
async def image(
    asset_id: str,
    size: str = Query("preview", pattern="^(preview|thumbnail)$"),
    config: VaultConfig = Depends(get_config),
    http=Depends(get_http),
) -> Response:
    if not config.immich.configured:
        raise HTTPException(status_code=503, detail="Immich ist nicht konfiguriert")
    try:
        proxied = await ImmichService(config.immich, http).image(asset_id, size=size)
    except ImmichError as exc:
        raise _immich_error(exc) from exc
    return Response(
        content=proxied.content,
        status_code=proxied.status_code,
        media_type=proxied.media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
