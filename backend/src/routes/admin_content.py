"""
Admin content-management, moderation, and upload routes (MOO-71).

Metadata edits and status changes are DB-side only. Uploads land on the
separate writable uploads volume, never on the read-only /music volume.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

import src.crud.content as crud
import src.crud.settings as settings_crud
from src.auth.permissions import require_permission
from src.schemas.admin import (
    AdminContentListResponse,
    AdminSongSchema,
    ContentMetadataUpdateSchema,
    ContentStatusUpdateSchema,
)
from src.schemas.users import UserOutSchema
from src.security import audit

router = APIRouter(prefix="/admin", tags=["admin: content"])

_edit = Depends(require_permission("edit_metadata"))
_moderate = Depends(require_permission("approve_submissions"))


@router.get("/content", response_model=AdminContentListResponse, dependencies=[_edit])
async def list_content(
    q: Optional[str] = Query(None, description="Search title/artist/album/genre"),
    status: Optional[str] = Query(
        None, description="published | draft | pending | rejected"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=300),
) -> AdminContentListResponse:
    """Every track (any status) with search and status filter."""
    return AdminContentListResponse(
        **await crud.list_content(q=q, status=status, page=page, page_size=page_size)
    )


@router.patch("/content/{song_id}/status", response_model=AdminSongSchema)
async def set_content_status(
    request: Request,
    song_id: int,
    payload: ContentStatusUpdateSchema,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> AdminSongSchema:
    """Toggle publish/draft (or set any moderation status)."""
    result = await crud.set_status(song_id, payload.status)
    await audit.audit_event(
        audit.CONTENT_STATUS_CHANGED,
        request=request,
        actor=actor,
        target_type="song",
        target_id=song_id,
        detail={"status": payload.status},
    )
    return AdminSongSchema(**result)


@router.patch("/content/{song_id}", response_model=AdminSongSchema)
async def edit_content_metadata(
    request: Request,
    song_id: int,
    payload: ContentMetadataUpdateSchema,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> AdminSongSchema:
    """
    Edit a track's tags in the database only (the file is never rewritten --
    the /music mount is read-only; writing tags back is MOO-75). Since MOO-82
    this covers the full ID3 field set including the custom TXXX frames, and
    every edit is recorded in the track's revision history.
    """
    return AdminSongSchema(
        **await crud.edit_metadata(song_id, payload, actor=actor, request=request)
    )


@router.post("/content/upload", response_model=AdminSongSchema)
async def upload_track(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    artist: Optional[str] = Form(None),
    album: Optional[str] = Form(None),
    genre: Optional[str] = Form(None),
    bpm: Optional[float] = Form(None),
    key: Optional[str] = Form(None),
    require_approval: Optional[bool] = Form(None),
    current_user: UserOutSchema = Depends(require_permission("upload_tracks")),
) -> AdminSongSchema:
    """
    Upload a track onto the writable uploads volume, parse its tags, and add
    it. When require_approval is set (or the instance requires approval) the
    track enters the moderation queue as pending instead of being published.
    """
    if require_approval is None:
        require_approval = bool(
            await settings_crud.get_value("general", "require_approval")
        )
    overrides = {
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "bpm": bpm,
        "musical_key": key,
    }
    created = await crud.upload_track(
        file, overrides, require_approval, current_user.id
    )
    await audit.audit_event(
        audit.CONTENT_UPLOADED,
        request=request,
        actor=current_user,
        target_type="song",
        target_id=created.get("id"),
        detail={"status": created.get("status")},
    )
    return AdminSongSchema(**created)


@router.get(
    "/moderation", response_model=AdminContentListResponse, dependencies=[_moderate]
)
async def moderation_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=300),
) -> AdminContentListResponse:
    """The pending submission queue."""
    return AdminContentListResponse(
        **await crud.moderation_queue(page=page, page_size=page_size)
    )


@router.post(
    "/content/{song_id}/approve",
    response_model=AdminSongSchema,
    dependencies=[_moderate],
)
async def approve_submission(song_id: int) -> AdminSongSchema:
    """Approve a pending submission: publish it."""
    return AdminSongSchema(**await crud.approve(song_id))


@router.post(
    "/content/{song_id}/reject",
    response_model=AdminSongSchema,
    dependencies=[_moderate],
)
async def reject_submission(song_id: int) -> AdminSongSchema:
    """Reject a submission: mark it rejected."""
    return AdminSongSchema(**await crud.reject(song_id))
