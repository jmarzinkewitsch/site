"""Credential and settings store for vault-api.

All foreign keys (Jellyfin, Radarr/Sonarr/Lidarr, TMDB, OMDb, Anthropic) live
here and are fed by the LAN web-config UI (see routers/admin.py) — never by the
tvOS app. Persisted as JSON; secrets stay out of git (see .gitignore).

Empty fields fall back to environment variables so the stack can be bootstrapped
from docker-compose before the web UI is opened.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_PATH = Path(os.environ.get("VAULT_CONFIG_PATH", "config.json"))

# Which env var seeds each empty field on first load (bootstrap convenience).
_ENV_BOOTSTRAP = {
    ("bearer_token",): "VAULT_BEARER_TOKEN",
    ("jellyfin", "base_url"): "JELLYFIN_URL",
    ("jellyfin", "api_key"): "JELLYFIN_TOKEN",
    ("jellyfin", "user_id"): "JELLYFIN_USER_ID",
    ("jellyfin", "device_id"): "JELLYFIN_DEVICE_ID",
    ("roon", "base_url"): "ROON_API_URL",
}


class ServiceConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)


class JellyfinConfig(ServiceConfig):
    # Jellyfin needs a user context for most library endpoints.
    user_id: str = ""
    device_id: str = "vault-api"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.user_id)


class UrlServiceConfig(BaseModel):
    base_url: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url)


class ArrDefaults(BaseModel):
    """Default Radarr/Sonarr add options chosen once in the admin UI (M4)."""
    quality_profile_id: int | None = None
    root_folder: str | None = None


class VaultConfig(BaseModel):
    # The single shared secret the tvOS app sends as `Authorization: Bearer …`.
    bearer_token: str = ""
    jellyfin: JellyfinConfig = Field(default_factory=JellyfinConfig)
    radarr: ServiceConfig = Field(default_factory=ServiceConfig)
    sonarr: ServiceConfig = Field(default_factory=ServiceConfig)
    lidarr: ServiceConfig = Field(default_factory=ServiceConfig)
    tmdb: ServiceConfig = Field(default_factory=ServiceConfig)
    omdb: ServiceConfig = Field(default_factory=ServiceConfig)
    anthropic: ServiceConfig = Field(default_factory=ServiceConfig)
    roon: UrlServiceConfig = Field(default_factory=UrlServiceConfig)
    radarr_defaults: ArrDefaults = Field(default_factory=ArrDefaults)
    sonarr_defaults: ArrDefaults = Field(default_factory=ArrDefaults)


def _apply_env_bootstrap(config: VaultConfig) -> VaultConfig:
    """Fill only still-empty fields from environment variables."""
    for path, env_name in _ENV_BOOTSTRAP.items():
        value = os.environ.get(env_name)
        if not value:
            continue
        target: object = config
        for part in path[:-1]:
            target = getattr(target, part)
        if not getattr(target, path[-1]):
            setattr(target, path[-1], value)
    return config


class ConfigStore:
    """Thread-safe JSON-backed config. Reads stay cheap; the web UI writes."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._config = self._load_from_disk()

    def _load_from_disk(self) -> VaultConfig:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                config = VaultConfig.model_validate(raw)
            except (json.JSONDecodeError, ValueError):
                config = VaultConfig()
        else:
            config = VaultConfig()
        return _apply_env_bootstrap(config)

    def get(self) -> VaultConfig:
        with self._lock:
            # Hand out a copy so callers can't mutate shared state in place.
            return self._config.model_copy(deep=True)

    def update(self, **sections: dict) -> VaultConfig:
        """Merge partial section dicts (e.g. jellyfin={"base_url": …}) and save."""
        with self._lock:
            current = self._config.model_dump()
            for key, value in sections.items():
                if isinstance(value, dict) and isinstance(current.get(key), dict):
                    current[key].update(value)
                else:
                    current[key] = value
            self._config = VaultConfig.model_validate(current)
            self._save_locked()
            return self._config.model_copy(deep=True)

    def ensure_bearer_token(self) -> str:
        """Create a bearer token if none exists yet; return the current one."""
        with self._lock:
            if not self._config.bearer_token:
                self._config.bearer_token = secrets.token_urlsafe(24)
                self._save_locked()
            return self._config.bearer_token

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._config.model_dump(), indent=2))
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)  # secrets file: owner-only
        except OSError:
            pass


def mask(value: str) -> str:
    """Redact a secret for display: keep nothing but the last 4 chars."""
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]
