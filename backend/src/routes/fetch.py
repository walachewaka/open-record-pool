"""
Member download routes (MOO-78): submit a provider URL and track your own
fetch queue. Submission is gated by the existing `upload_tracks` permission
(fetching a URL into the library is semantically a remote upload) plus the
per-provider enable flags, a rate limit, and a per-user daily quota. Every
route declares its authorization (MOO-89 route guard).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.auth.jwthandler import get_current_user
from src.auth.permissions import has_permission, require_permission
from src.crud import downloads as downloads_crud
from src.downloads import service
from src.downloads.service import DownloadPolicyError
from src.schemas.downloads import (
    DownloadRequestList,
    DownloadRequestOut,
    FetchSubmitIn,
    ProvidersOut,
)
from src.schemas.users import UserOutSchema

router = APIRouter(prefix="/fetch", tags=["downloads"])


@router.post("", response_model=DownloadRequestOut, status_code=202)
async def submit_fetch(
    payload: FetchSubmitIn,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("upload_tracks")),
) -> DownloadRequestOut:
    """Submit a YouTube/SoundCloud/Spotify track URL to fetch into the library."""
    try:
        req = await service.enqueue_download(
            payload.url,
            requested_by_id=current_user.id,
            origin="member",
            enforce_user_policy=True,
            request=request,
        )
    except DownloadPolicyError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail)
    req = await downloads_crud.get_request(req.id)
    return downloads_crud.serialize(req, include_metadata=True)


@router.get("", response_model=DownloadRequestList)
async def list_my_requests(
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> DownloadRequestList:
    """My download requests, newest first (keyset paginated)."""
    items, next_cursor = await downloads_crud.list_mine(
        current_user.id, status=status, cursor=cursor, limit=limit
    )
    return DownloadRequestList(items=items, next_cursor=next_cursor)


@router.get("/providers", response_model=ProvidersOut)
async def get_providers(
    current_user: UserOutSchema = Depends(get_current_user),
) -> ProvidersOut:
    """Download availability for the UI gate (declared before /fetch/{id})."""
    return ProvidersOut(**await service.providers_status(current_user.id))


@router.get("/{request_id}", response_model=DownloadRequestOut)
async def get_request(
    request_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> DownloadRequestOut:
    """One request with its source metadata. Owner or view_reports only."""
    req = await downloads_crud.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Download request not found")
    if req.requested_by_id != current_user.id and not await has_permission(
        current_user, "view_reports"
    ):
        raise HTTPException(
            status_code=403, detail="You do not have permission: view_reports"
        )
    return downloads_crud.serialize(req, include_metadata=True)


async def _owner_or(current_user, req, permission):
    if req.requested_by_id != current_user.id and not await has_permission(
        current_user, permission
    ):
        raise HTTPException(
            status_code=403, detail="You do not have permission: {}".format(permission)
        )


@router.post("/{request_id}/cancel", response_model=DownloadRequestOut)
async def cancel(
    request_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> DownloadRequestOut:
    req = await downloads_crud.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Download request not found")
    await _owner_or(current_user, req, "approve_submissions")
    await downloads_crud.cancel_request(req)
    req = await downloads_crud.get_request(request_id)
    return downloads_crud.serialize(req, include_metadata=True)


@router.post("/{request_id}/retry", response_model=DownloadRequestOut)
async def retry(
    request_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> DownloadRequestOut:
    req = await downloads_crud.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Download request not found")
    await _owner_or(current_user, req, "approve_submissions")
    from src.security import audit

    await downloads_crud.retry_request(req)
    await audit.audit_event(
        "download.retried",
        actor=current_user,
        target_type="download",
        target_id=request_id,
    )
    req = await downloads_crud.get_request(request_id)
    return downloads_crud.serialize(req, include_metadata=True)
