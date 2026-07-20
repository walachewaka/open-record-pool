"""
Admin song request moderation (MOO-81): the pending queue, approve/reject/
retry/bulk actions, and the stats endpoint feeding the sidebar badge. Reuses
the existing `approve_submissions` permission (no new permission key, no
matrix migration). `/stats` and `/bulk` are declared before `/{request_id}/*`
for readability (same convention as `/fetch/providers`).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.auth.permissions import require_permission
from src.crud import song_requests as song_requests_crud
from src.schemas.song_requests import (
    AdminRequestListResponse,
    AdminRequestOut,
    ApproveSchema,
    BulkActionSchema,
    BulkResultOut,
    RejectSchema,
    RequestStatsOut,
)
from src.schemas.users import UserOutSchema

router = APIRouter(prefix="/admin/requests", tags=["admin: requests"])


@router.get("", response_model=AdminRequestListResponse)
async def list_all_requests(
    status: Optional[str] = Query("pending"),
    q: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(require_permission("approve_submissions")),
) -> AdminRequestListResponse:
    """Every request across all users, newest first."""
    items, next_cursor = await song_requests_crud.admin_list(
        status=status, q=q, cursor=cursor, limit=limit
    )
    return AdminRequestListResponse(items=items, next_cursor=next_cursor)


@router.get("/stats", response_model=RequestStatsOut)
async def request_stats(
    current_user: UserOutSchema = Depends(require_permission("approve_submissions")),
) -> RequestStatsOut:
    """The pending count feeding the admin sidebar badge."""
    return RequestStatsOut(**await song_requests_crud.admin_stats())


async def _get_or_404(request_id):
    req = await song_requests_crud.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


@router.post("/bulk", response_model=BulkResultOut)
async def bulk_action(
    payload: BulkActionSchema,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("approve_submissions")),
) -> BulkResultOut:
    result = await song_requests_crud.bulk(
        payload.ids,
        payload.action,
        current_user,
        reason=payload.reason,
        request=request,
    )
    return BulkResultOut(**result)


@router.post("/{request_id}/approve", response_model=AdminRequestOut)
async def approve_request(
    request_id: int,
    payload: ApproveSchema,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("approve_submissions")),
) -> AdminRequestOut:
    req = await _get_or_404(request_id)
    req = await song_requests_crud.approve(
        req, current_user, source_url=payload.source_url, request=request
    )
    return song_requests_crud.serialize(req, admin=True)


@router.post("/{request_id}/reject", response_model=AdminRequestOut)
async def reject_request(
    request_id: int,
    payload: RejectSchema,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("approve_submissions")),
) -> AdminRequestOut:
    req = await _get_or_404(request_id)
    req = await song_requests_crud.reject(
        req, current_user, reason=payload.reason, request=request
    )
    return song_requests_crud.serialize(req, admin=True)


@router.post("/{request_id}/retry", response_model=AdminRequestOut)
async def retry_request(
    request_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("approve_submissions")),
) -> AdminRequestOut:
    req = await _get_or_404(request_id)
    req = await song_requests_crud.retry(req, current_user, request=request)
    return song_requests_crud.serialize(req, admin=True)
