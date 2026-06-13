"""Admin web-config UI (LAN).

Credentials are entered here, not on the Apple TV. Reachable on the LAN only;
it is intentionally not behind the vault bearer token (that token is *generated*
here). Put it behind a reverse proxy / network ACL for anything beyond a home LAN.
"""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from cache import Cache
from config import ConfigStore, VaultConfig, mask
from deps import get_cache, get_config, get_http, get_store
from services.arr import ArrError
from services.jellyfin import JellyfinError, JellyfinService
from services.radarr import RadarrService
from services.sonarr import SonarrService
from services.tmdb import TmdbError, TmdbService

router = APIRouter(prefix="/admin", tags=["admin"])
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "web" / "templates"))

# Services that take a plain base_url + api_key (everything except Jellyfin).
_SIMPLE_SERVICES = ("radarr", "sonarr", "lidarr", "tmdb", "omdb", "anthropic")


def _redacted(config: VaultConfig) -> dict:
    """Config for display: secrets masked, non-secret fields shown in full."""
    out: dict = {
        "bearer_token": {"set": bool(config.bearer_token), "masked": mask(config.bearer_token)},
        "jellyfin": {
            "base_url": config.jellyfin.base_url,
            "user_id": config.jellyfin.user_id,
            "device_id": config.jellyfin.device_id,
            "api_key_set": bool(config.jellyfin.api_key),
            "api_key_masked": mask(config.jellyfin.api_key),
            "configured": config.jellyfin.configured,
        },
    }
    for name in _SIMPLE_SERVICES:
        cfg = getattr(config, name)
        out[name] = {
            "base_url": cfg.base_url,
            "api_key_set": bool(cfg.api_key),
            "api_key_masked": mask(cfg.api_key),
            "configured": cfg.configured,
        }
    return out


@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request, config: VaultConfig = Depends(get_config)) -> HTMLResponse:
    return _templates.TemplateResponse(
        request, "admin.html", {"config": _redacted(config)}
    )


@router.get("/config")
async def get_admin_config(config: VaultConfig = Depends(get_config)) -> dict:
    return _redacted(config)


@router.post("/config")
async def set_admin_config(
    sections: dict = Body(...),
    store: ConfigStore = Depends(get_store),
) -> dict:
    """Merge partial section dicts. The UI omits secret fields it isn't changing,
    so a blank field never clobbers a stored key by accident."""
    allowed = {"jellyfin", "radarr", "sonarr", "lidarr", "tmdb", "omdb", "anthropic",
               "radarr_defaults", "sonarr_defaults"}
    clean = {k: v for k, v in sections.items() if k in allowed and isinstance(v, dict)}
    config = store.update(**clean)
    return _redacted(config)


@router.post("/token")
async def generate_token(store: ConfigStore = Depends(get_store)) -> dict:
    """Create the bearer token if absent and return it in full (LAN admin only)."""
    token = store.ensure_bearer_token()
    return {"bearer_token": token}


@router.post("/test/{service}")
async def test_connection(
    service: str,
    config: VaultConfig = Depends(get_config),
    cache: Cache = Depends(get_cache),
    http: httpx.AsyncClient = Depends(get_http),
) -> dict:
    if service == "redis":
        ok = await cache.ping()
        return {"ok": ok, "detail": "verbunden" if ok else "nicht erreichbar"}
    if service == "jellyfin":
        if not config.jellyfin.configured:
            return {"ok": False, "detail": "URL, Token und User-ID nötig"}
        try:
            ok = await JellyfinService(config.jellyfin, http).ping()
            return {"ok": ok, "detail": "verbunden" if ok else "keine Antwort"}
        except JellyfinError as exc:
            return {"ok": False, "detail": exc.message}
    if service == "tmdb":
        if not config.tmdb.api_key:
            return {"ok": False, "detail": "API-Key nötig"}
        try:
            ok = await TmdbService(config.tmdb, http).ping()
            return {"ok": ok, "detail": "verbunden" if ok else "keine Antwort"}
        except TmdbError as exc:
            return {"ok": False, "detail": exc.message}
    if service in ("radarr", "sonarr"):
        cfg = getattr(config, service)
        if not cfg.configured:
            return {"ok": False, "detail": "URL und API-Key nötig"}
        arr_cls = RadarrService if service == "radarr" else SonarrService
        try:
            ok = await arr_cls(cfg.base_url, cfg.api_key, http).ping()
            return {"ok": ok, "detail": "verbunden" if ok else "keine Antwort"}
        except ArrError as exc:
            return {"ok": False, "detail": exc.message}
    # Lidarr/OMDb/Anthropic connection tests arrive with their services (M5/M8).
    return {"ok": False, "detail": "Test folgt mit der Anbindung dieses Dienstes"}
