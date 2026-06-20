"""Persona mini-profile endpoints (janno / tanno)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import require_bearer
from deps import get_profile_store
from models import PersonaProfile
from services.profile_store import ProfileStore, VALID_PERSONS

router = APIRouter(prefix="/profiles", tags=["profiles"], dependencies=[Depends(require_bearer)])


@router.get("", response_model=list[PersonaProfile])
async def list_profiles(store: ProfileStore = Depends(get_profile_store)) -> list[PersonaProfile]:
    """Return both persona profiles (with sensible defaults if unset)."""
    return store.list_all()


@router.put("/{person}", response_model=PersonaProfile)
async def upsert_profile(
    person: str,
    body: PersonaProfile,
    store: ProfileStore = Depends(get_profile_store),
) -> PersonaProfile:
    """Persist a persona mini-profile. person must be \'janno\' or \'tanno\'."""
    if person not in VALID_PERSONS:
        raise HTTPException(status_code=422, detail=f"person muss janno oder tanno sein, nicht {person!r}")
    if body.person != person:
        raise HTTPException(status_code=422, detail="person im Body muss mit URL-Parameter übereinstimmen")
    return store.upsert(body)
