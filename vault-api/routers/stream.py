"""GET /stream/{id} — hand the player a fresh direct-stream URL.

Deliberately uncached: the URL carries Jellyfin's (time-bound) api_key, so a new
one is minted per request. Only the URL travels through vault-api — the video
bytes flow straight from Jellyfin to the app over the LAN.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from auth import require_bearer
from deps import get_jellyfin
from models import StreamInfo
from services.jellyfin import JellyfinService

router = APIRouter(prefix="/stream", tags=["stream"], dependencies=[Depends(require_bearer)])


@router.get("/{item_id}", response_model=StreamInfo)
async def stream(
    item_id: str,
    media_source_id: str | None = Query(default=None),
    jellyfin: JellyfinService = Depends(get_jellyfin),
) -> StreamInfo:
    return jellyfin.stream(item_id, media_source_id)
