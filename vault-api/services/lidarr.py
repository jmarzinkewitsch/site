from __future__ import annotations

from services.arr import ArrClient


class LidarrService(ArrClient):
    media_type = "Music"
    api_version = "v1"
