"""Cast-to-Apple-TV router.

POST /cast/appletv wakes the Apple TV via HA, switches it to the Vault app, and
parks a short-lived "pending" command in app.state. The tvOS Vault app polls
GET /cast/appletv/pending (full bearer only) and consumes it once, then resumes
the film from Jellyfin. The pending store is in-memory and intentionally
ephemeral — it's read within seconds of the cast.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_bearer, require_bearer_or_kiosk
from config import VaultConfig
from deps import get_config, get_homeassistant
from models import CastPending, CastRequest, CastResult, CastStatus
from services.homeassistant import HomeAssistantError, HomeAssistantService

router = APIRouter(prefix="/cast", tags=["cast"])

# States that mean the Apple TV is not actively reachable for playback.
_OFFLINE_STATES = {"off", "unavailable", "standby"}


@router.post("/appletv", response_model=CastResult, dependencies=[Depends(require_bearer_or_kiosk)])
async def cast_appletv(
    body: CastRequest,
    request: Request,
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> CastResult:
    cfg = config.cast
    try:
        await ha.launch_apple_tv(cfg.appletv_entity, cfg.appletv_source)
        state = await ha.media_player_state(cfg.appletv_entity)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    request.app.state.cast_pending = {
        "item_id": body.item_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return CastResult(ok=True, item_id=body.item_id, appletv=state.state if state else None)


@router.get("/appletv/pending", response_model=CastPending, dependencies=[Depends(require_bearer)])
async def cast_pending(request: Request) -> CastPending:
    pending = getattr(request.app.state, "cast_pending", None)
    request.app.state.cast_pending = None  # consume-once
    if not pending:
        return CastPending(item_id=None, created_at=None)
    return CastPending(**pending)


@router.get("/appletv/status", response_model=CastStatus, dependencies=[Depends(require_bearer_or_kiosk)])
async def cast_status(
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> CastStatus:
    try:
        state = await ha.media_player_state(config.cast.appletv_entity)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if state is None:
        return CastStatus(online=False, state="unknown", app=None)
    return CastStatus(
        online=state.state not in _OFFLINE_STATES,
        state=state.state,
        app=state.attributes.get("app_name"),
    )
