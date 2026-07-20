"""
Member song request routes (MOO-81): submit a request, track your own
queue, cancel a still-pending one, and the summary/seen pair that back the
sidebar badge + toast. Every route declares its authorization (MOO-89 route
guard). `/mine*` is declared before `/{request_id}` so the literal path isn't
shadowed by the int param (same trick as `/songs/genres`).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from src.auth.jwthandler import get_current_user
from src.crud import song_requests as song_requests_crud
from src.schemas.song_requests import (
    MarkSeenOut,
    RequestCreateSchema,
    RequestListResponse,
    RequestOut,
    RequestSummaryOut,
)
from src.schemas.users import UserOutSchema

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=RequestOut, status_code=201)
async def submit_request(
    payload: RequestCreateSchema,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
) -> RequestOut:
    """Submit a free-text or URL song request."""
    req = await song_requests_crud.create_request(
        current_user, payload, request=request
    )
    return song_requests_crud.serialize(req)


@router.get("/mine", response_model=RequestListResponse)
async def list_my_requests(
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> RequestListResponse:
    """My requests, newest first (keyset paginated)."""
    items, next_cursor = await song_requests_crud.list_mine(
        current_user.id, status=status, cursor=cursor, limit=limit
    )
    return RequestListResponse(items=items, next_cursor=next_cursor)


@router.get("/mine/summary", response_model=RequestSummaryOut)
async def my_summary(
    current_user: UserOutSchema = Depends(get_current_user),
) -> RequestSummaryOut:
    """Open/unseen-resolved counts feeding the sidebar badge."""
    data = await song_requests_crud.summary(current_user.id)
    return RequestSummaryOut(**data)


@router.post("/mine/seen", response_model=MarkSeenOut)
async def mark_seen(
    current_user: UserOutSchema = Depends(get_current_user),
) -> MarkSeenOut:
    """Clear the unseen badge: mark every terminal request as seen."""
    updated = await song_requests_crud.mark_seen(current_user.id)
    return MarkSeenOut(updated=updated)


@router.get("/{request_id}", response_model=RequestOut)
async def get_request(
    request_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> RequestOut:
    """Owner or approve_submissions only; unknown/foreign id -> 404 (IDOR-safe)."""
    req = await song_requests_crud.get_for_user_or_404(
        request_id, current_user, allow_permission="approve_submissions"
    )
    return song_requests_crud.serialize(req)


@router.post("/{request_id}/cancel", response_model=RequestOut)
async def cancel_request(
    request_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
) -> RequestOut:
    """Owner-only; moderators use reject instead."""
    req = await song_requests_crud.get_for_user_or_404(request_id, current_user)
    req = await song_requests_crud.cancel(req, current_user, request=request)
    return song_requests_crud.serialize(req)
