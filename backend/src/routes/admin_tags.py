"""
The metadata editor's admin API (MOO-82): edit history and rollback, batch
edits, album-art management, Beatport-backed field suggestions, and the
member-proposal review queue.

Edits themselves keep the existing route (PATCH /admin/content/{id}); this
module adds everything around them. Gated by `edit_metadata`, the permission
that already owns DB-side metadata edits -- no new permission key.

Security bar (MOO-89 / SECURITY.md): every route declares its guard (item 1);
art upload and candidate fetch are rate limited (item 5); every mutation is
audited (item 6); art bytes are sniffed by magic number, capped, and re-encoded
before they are ever stored (item 3), and a candidate URL is only fetched when
Beatport itself gave it to us for that track (item 9).
"""
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)

import src.crud.content as content_crud
import src.crud.tags as crud
from src.auth.permissions import require_permission
from src.schemas.admin import AdminSongSchema
from src.schemas.tags import (
    ArtCandidateListResponse,
    ArtSelectSchema,
    BATCH_FIELDS,
    BatchEditResponse,
    BatchEditSchema,
    BatchRollbackResponse,
    ProposalListResponse,
    ProposalSchema,
    RevisionListResponse,
    SuggestionListResponse,
)
from src.schemas.users import UserOutSchema
from src.security.ratelimit import rate_limit
from src.utils import artwork as art_utils

router = APIRouter(prefix="/admin", tags=["admin: metadata editor"])

_edit = Depends(require_permission("edit_metadata"))


async def _song_response(song):
    counts = await content_crud._download_counts([song.id])
    statuses = await content_crud._enrichment_statuses([song.id])
    return AdminSongSchema(
        **content_crud._admin_song_dict(
            song, counts.get(song.id, 0), statuses.get(song.id)
        )
    )


# --- History -----------------------------------------------------------------


@router.get(
    "/content/{song_id}/revisions",
    response_model=RevisionListResponse,
    dependencies=[_edit],
)
async def list_revisions(
    song_id: int,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
) -> RevisionListResponse:
    """A track's edit history, newest first: who changed what, old -> new."""
    await crud.get_song_or_404(song_id)
    return RevisionListResponse(**await crud.list_revisions(song_id, cursor, limit))


@router.post(
    "/content/{song_id}/revisions/{revision_id}/rollback",
    response_model=AdminSongSchema,
)
async def rollback_revision(
    request: Request,
    song_id: int,
    revision_id: int,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> AdminSongSchema:
    """Undo one edit, as a new revision. 409 when the track moved on since."""
    song, _revision = await crud.rollback_revision(
        revision_id, actor=actor, request=request
    )
    if song.id != song_id:
        raise HTTPException(status_code=404, detail="Revision not found")
    return await _song_response(song)


@router.post(
    "/content/batches/{batch_id}/rollback", response_model=BatchRollbackResponse
)
async def rollback_batch(
    request: Request,
    batch_id: str,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> BatchRollbackResponse:
    """Undo a whole batch edit. Tracks edited again since are skipped."""
    return BatchRollbackResponse(
        **await crud.rollback_batch(batch_id, actor=actor, request=request)
    )


# --- Batch edit --------------------------------------------------------------


@router.post("/content/tags/batch", response_model=BatchEditResponse)
async def batch_edit(
    request: Request,
    payload: BatchEditSchema,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> BatchEditResponse:
    """Set a few release-level fields on a multi-selection of tracks."""
    changes = payload.fields.dict(exclude_unset=True)
    invalid = [f for f in changes if f not in BATCH_FIELDS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail="Not a batch-editable field: {}".format(", ".join(sorted(invalid))),
        )
    if not changes:
        raise HTTPException(status_code=422, detail="No fields to set")
    return BatchEditResponse(
        **await crud.edit_batch(
            set(payload.song_ids), changes, actor=actor, request=request
        )
    )


# --- Album art ---------------------------------------------------------------


@router.get(
    "/content/{song_id}/artwork/candidates",
    response_model=ArtCandidateListResponse,
    dependencies=[_edit],
)
async def artwork_candidates(song_id: int) -> ArtCandidateListResponse:
    """Every cover on offer for this track. Reads only -- no network calls."""
    song = await crud.get_song_or_404(song_id)
    return ArtCandidateListResponse(items=await crud.artwork_candidates(song))


@router.put("/content/{song_id}/artwork", response_model=AdminSongSchema)
async def upload_artwork(
    request: Request,
    song_id: int,
    file: UploadFile = File(...),
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> AdminSongSchema:
    """Replace a track's cover with an uploaded JPEG/PNG (re-encoded, capped)."""
    await rate_limit("art_upload", str(actor.id), 30, 300)
    song = await crud.get_song_or_404(song_id)
    data = await file.read(art_utils.MAX_UPLOAD_BYTES + 1)
    await crud.set_artwork_bytes(song, data, "upload", actor=actor, request=request)
    return await _song_response(song)


@router.post("/content/{song_id}/artwork/select", response_model=AdminSongSchema)
async def select_artwork(
    request: Request,
    song_id: int,
    payload: ArtSelectSchema,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> AdminSongSchema:
    """Adopt one of the offered candidates (the embedded APIC, or a Beatport cover)."""
    await rate_limit("art_fetch", str(actor.id), 20, 60)
    song = await crud.get_song_or_404(song_id)
    await crud.select_artwork(
        song, payload.origin, url=payload.url, actor=actor, request=request
    )
    return await _song_response(song)


@router.delete("/content/{song_id}/artwork", response_model=AdminSongSchema)
async def delete_artwork(
    request: Request,
    song_id: int,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> AdminSongSchema:
    """Drop the track's cover (the polluted-art case). The file keeps its APIC."""
    song = await crud.get_song_or_404(song_id)
    await crud.remove_artwork(song, actor=actor, request=request)
    return await _song_response(song)


# --- Enrichment suggestions --------------------------------------------------


@router.get(
    "/content/{song_id}/suggestions",
    response_model=SuggestionListResponse,
    dependencies=[_edit],
)
async def suggestions(song_id: int) -> SuggestionListResponse:
    """
    Per-field values Beatport matched for this track (MOO-85), each against the
    current value. Applying one is an ordinary edit (PATCH /admin/content/{id}),
    so it locks the field and lands in the history like any other.
    """
    song = await crud.get_song_or_404(song_id)
    return SuggestionListResponse(**await crud.suggestions(song))


# --- Member proposals --------------------------------------------------------


@router.get("/tag-proposals", response_model=ProposalListResponse, dependencies=[_edit])
async def list_proposals(
    status: Optional[str] = Query("pending"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
) -> ProposalListResponse:
    """The queue of member-suggested edits."""
    return ProposalListResponse(
        **await crud.list_proposals(status=status, cursor=cursor, limit=limit)
    )


@router.post("/tag-proposals/{proposal_id}/approve", response_model=ProposalSchema)
async def approve_proposal(
    request: Request,
    proposal_id: int,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> ProposalSchema:
    """Accept a suggestion: it lands as an ordinary edit, credited to its author."""
    return ProposalSchema(
        **await crud.review_proposal(proposal_id, True, actor, request=request)
    )


@router.post("/tag-proposals/{proposal_id}/reject", response_model=ProposalSchema)
async def reject_proposal(
    request: Request,
    proposal_id: int,
    actor: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> ProposalSchema:
    """Decline a suggestion. The track is untouched."""
    return ProposalSchema(
        **await crud.review_proposal(proposal_id, False, actor, request=request)
    )
