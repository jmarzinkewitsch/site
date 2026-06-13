"""GET /health — liveness plus a per-service status line.

Unauthenticated on purpose: it's the probe a container orchestrator hits, and
it must work before any bearer token is configured.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from cache import Cache
from config import VaultConfig
from deps import get_cache, get_config, get_http
from models import HealthResponse, ServiceStatus
from services.jellyfin import JellyfinError, JellyfinService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    config: VaultConfig = Depends(get_config),
    cache: Cache = Depends(get_cache),
    http=Depends(get_http),
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

    # Services that are configured but not yet wired up (M4+).
    for name, cfg in (
        ("radarr", config.radarr), ("sonarr", config.sonarr), ("lidarr", config.lidarr),
        ("tmdb", config.tmdb), ("omdb", config.omdb), ("anthropic", config.anthropic),
    ):
        if cfg.configured:
            services.append(ServiceStatus(name=name, configured=True, ok=False,
                                          detail="konfiguriert, Anbindung folgt"))

    # "ok" only requires the critical path (Jellyfin); everything else may degrade.
    status = "ok" if (jf_ok or not jf_configured) else "degraded"
    return HealthResponse(status=status, services=services)
