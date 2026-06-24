"""Bearer-token middleware.

The tvOS app authenticates with the single shared vault bearer token (generated
in the admin UI). Everything app-facing depends on `require_bearer`.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Query

from config import VaultConfig
from deps import get_config


def require_bearer(
    config: VaultConfig = Depends(get_config),
    authorization: str | None = Header(default=None),
) -> None:
    if not config.bearer_token:
        raise HTTPException(status_code=503, detail="vault-api ist noch nicht konfiguriert")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Bearer-Token fehlt")
    # Constant-time compare so a wrong token can't be guessed by timing.
    if not hmac.compare_digest(token, config.bearer_token):
        raise HTTPException(status_code=401, detail="Ungültiger Token")


def require_bearer_or_kiosk(
    config: VaultConfig = Depends(get_config),
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    if not config.bearer_token and not config.kiosk_token:
        raise HTTPException(status_code=503, detail="vault-api ist noch nicht konfiguriert")
    scheme, _, bearer_token = (authorization or "").partition(" ")
    candidate = bearer_token if scheme.lower() == "bearer" and bearer_token else token
    if not candidate:
        raise HTTPException(status_code=401, detail="Bearer-Token fehlt")
    if config.bearer_token and hmac.compare_digest(candidate, config.bearer_token):
        return
    if config.kiosk_token and hmac.compare_digest(candidate, config.kiosk_token):
        return
    raise HTTPException(status_code=401, detail="Ungültiger Token")
