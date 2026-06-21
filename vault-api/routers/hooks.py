"""Jellyfin webhook receiver.

Configure in Jellyfin → Dashboard → Webhook-Plugin:
  URL:     http://<vault-host>/hooks/jellyfin
  Header:  Authorization: Bearer <vault-bearer-token>
  Events:  Item Added

When Jellyfin fires "Item Added" vault flushes the library caches so the
tvOS app sees the new content immediately on next load.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import require_bearer
from cache import Cache
from deps import get_cache

router = APIRouter(prefix="/hooks", tags=["hooks"], dependencies=[Depends(require_bearer)])

# Cache prefixes that cover the full browse library.
_LIBRARY_PREFIXES = (
    "lib:series:",
    "lib:movies:",
    "lib:latest:",
    "lib:shelf:",
    "lib:nextup:",
    "recommend:",
)


@router.post("/jellyfin")
async def jellyfin_webhook(
    payload: dict,
    cache: Cache = Depends(get_cache),
) -> dict:
    """Accepts any Jellyfin webhook event and flushes library caches on ItemAdded."""
    event = payload.get("NotificationType") or payload.get("Event") or ""

    if event == "ItemAdded":
        for prefix in _LIBRARY_PREFIXES:
            await cache.invalidate_prefix(prefix)
        item_type = payload.get("ItemType", "unknown")
        item_name = payload.get("Name", "unknown")
        return {"flushed": True, "item": item_name, "type": item_type}

    return {"flushed": False, "event": event}
