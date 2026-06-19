"""GET /health — liveness plus a per-service status line.

Unauthenticated on purpose: it's the probe a container orchestrator hits, and
it must work before any bearer token is configured.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from cache import Cache
from config import VaultConfig
from deps import get_cache, get_config, get_http
from models import HealthResponse, ServiceStatus
from services.arr import ArrError
from services.jellyfin import JellyfinError, JellyfinService
from services.lidarr import LidarrService
from services.radarr import RadarrService
from services.roon import RoonService
from services.sonarr import SonarrService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    config: VaultConfig = Depends(get_config),
    cache: Cache = Depends(get_cache),
    http: httpx.AsyncClient = Depends(get_http),
) -> HealthResponse:
    services: list[ServiceStatus] = []

    # Jellyfin — the one service in the critical path for playback.
    jf_configured = config.jellyfin.configured
    jf_ok = False
    jf_detail = None
    if jf_configured:
        try:
            jf_ok = await JellyfinService(config.jellyfin, http).ping()
        except JellyfinError as exc:
            jf_detail = exc.message
    services.append(
        ServiceStatus(name="jellyfin", configured=jf_configured, ok=jf_ok, detail=jf_detail)
    )

    # Redis — caching only; absence degrades but doesn't break.
    redis_ok = await cache.ping()
    services.append(
        ServiceStatus(name="redis", configured=True, ok=redis_ok,
                      detail=None if redis_ok else "kein Cache (degradiert)")
    )

    roon_ok = False
    if config.roon.configured:
        roon_ok = await RoonService(config.roon, http).ping()
    services.append(
        ServiceStatus(
            name="roon",
            configured=config.roon.configured,
            ok=roon_ok,
            detail=None if roon_ok or not config.roon.configured else "keine Antwort",
        )
    )

    for name, cfg, cls in (
        ("radarr", config.radarr, RadarrService),
        ("sonarr", config.sonarr, SonarrService),
        ("lidarr", config.lidarr, LidarrService),
    ):
        if cfg.configured:
            ok = False
            detail = None
            try:
                ok = await cls(cfg.base_url, cfg.api_key, http).ping()
            except ArrError as exc:
                detail = exc.message
            services.append(ServiceStatus(name=name, configured=True, ok=ok, detail=detail))

    # Optional services wired into feature-specific routes.
    for name, cfg in (
        ("tmdb", config.tmdb), ("omdb", config.omdb), ("anthropic", config.anthropic),
    ):
        if cfg.configured:
            services.append(ServiceStatus(name=name, configured=True, ok=False,
                                          detail="konfiguriert, Anbindung folgt"))

    # "ok" only requires the critical path (Jellyfin); everything else may degrade.
    status = "ok" if (jf_ok or not jf_configured) else "degraded"
    return HealthResponse(status=status, services=services)
