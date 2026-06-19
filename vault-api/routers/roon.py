from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response

from auth import require_bearer
from deps import get_roon
from services.roon import RoonError, RoonService

router = APIRouter(prefix="/roon", tags=["roon"], dependencies=[Depends(require_bearer)])


@router.api_route("", methods=["GET", "POST"])
@router.api_route("/{path:path}", methods=["GET", "POST"])
async def roon_proxy(
    request: Request,
    path: str = "",
    body: Any = Body(default=None),
    roon: RoonService = Depends(get_roon),
) -> Response:
    try:
        proxied = await roon.proxy(
            request.method,
            path,
            params=dict(request.query_params),
            json=body if request.method in {"POST", "PUT", "PATCH"} else None,
        )
    except RoonError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Response(
        content=proxied.content,
        status_code=proxied.status_code,
        media_type=proxied.media_type,
    )
