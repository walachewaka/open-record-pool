"""
Member-facing half of the metadata editor (MOO-82): the album-art image itself,
and edit suggestions.

Members cannot write tags -- that is `edit_metadata`. What they can do is
propose an edit ("this is the extended mix, not the radio edit") and let a
curator approve it, which is how a shared pool stays curated without handing
every user write access to the library's metadata.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

import src.crud.tags as crud
from src.auth.jwthandler import get_current_user
from src.auth.permissions import can_view_unpublished
from src.schemas.tags import ProposalCreateSchema, ProposalListResponse, ProposalSchema
from src.schemas.users import UserOutSchema
from src.security import audit
from src.security.ratelimit import rate_limit

router = APIRouter(tags=["metadata editor"])


@router.get("/songs/{song_id}/artwork")
async def get_song_artwork(
    song_id: int, current_user: UserOutSchema = Depends(get_current_user)
):
    """
    The track's cover image. Same read access as the track itself -- album art
    is never a static (unauthenticated) mount.
    """
    song = await crud.get_song_or_404(song_id)
    if song.status != "published" and not await can_view_unpublished(current_user):
        raise HTTPException(status_code=404, detail="Song not found")
    if not song.artwork_path:
        raise HTTPException(status_code=404, detail="This track has no album art")
    return FileResponse(
        song.artwork_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/songs/{song_id}/tag-proposals", response_model=ProposalSchema)
async def create_tag_proposal(
    request: Request,
    song_id: int,
    payload: ProposalCreateSchema,
    current_user: UserOutSchema = Depends(get_current_user),
) -> ProposalSchema:
    """Suggest a metadata correction on a track. A curator reviews it."""
    await rate_limit("tag_proposal", str(current_user.id), 10, 3600)
    proposal = await crud.create_proposal(
        song_id,
        payload.changes.dict(exclude_unset=True),
        payload.note,
        current_user,
    )
    await audit.audit_event(
        audit.TAG_PROPOSAL_CREATED,
        request=request,
        actor=current_user,
        target_type="song",
        target_id=song_id,
        detail={"proposal": proposal.id, "fields": sorted(proposal.changes or {})},
    )
    page = await crud.list_proposals(proposer_id=current_user.id, limit=1)
    return ProposalSchema(**page["items"][0])


@router.get("/users/me/tag-proposals", response_model=ProposalListResponse)
async def list_my_tag_proposals(
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> ProposalListResponse:
    """The suggestions I submitted, and what became of them."""
    return ProposalListResponse(
        **await crud.list_proposals(
            status=status, proposer_id=current_user.id, cursor=cursor, limit=limit
        )
    )
