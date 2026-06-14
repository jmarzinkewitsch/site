"""Vault-owned rating snapshot endpoints.

Snapshots are independent from Jellyfin ratings and persist profile-specific
Janno/Tanno values plus metadata needed to reconnect a title later.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_bearer
from deps import get_cache, get_rating_store
from cache import Cache
from models import RatingSnapshot, RatingSnapshotBody
from services.rating_store import RatingStore

router = APIRouter(prefix="/ratings", tags=["ratings"], dependencies=[Depends(require_bearer)])


@router.post("/item/{item_id}/snapshot", response_model=RatingSnapshot, status_code=status.HTTP_201_CREATED)
async def save_snapshot(
    item_id: str,
    body: RatingSnapshotBody,
    store: RatingStore = Depends(get_rating_store),
    cache: Cache = Depends(get_cache),
) -> RatingSnapshot:
    snapshot = store.upsert(item_id=item_id, **body.model_dump())
    await cache.invalidate_prefix("recommend:")
    return snapshot


@router.get("/item/{item_id}/snapshot", response_model=RatingSnapshot)
async def get_snapshot(
    item_id: str,
    store: RatingStore = Depends(get_rating_store),
) -> RatingSnapshot:
    snapshot = store.get(item_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Rating-Snapshot nicht gefunden")
    return snapshot


@router.get("/snapshots", response_model=list[RatingSnapshot])
async def list_snapshots(store: RatingStore = Depends(get_rating_store)) -> list[RatingSnapshot]:
    return store.list()
