"""
The admin duplicates surface (MOO-90): review queue, candidate detail,
resolve/bulk-resolve, per-recording version history with one-click promote,
and the retro-dedup backfill trigger.

Security bar (MOO-89 / SECURITY.md): every route declares its guard (item
1) -- duplicate resolution is content-metadata stewardship, so it reuses
edit_metadata; the instance-wide backfill needs site_settings like the scan.
Resolution endpoints never touch the filesystem (D6), every decision is
audited (item 6), and the backfill trigger is rate limited (item 5).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import src.crud.dedup as dedup_crud
from src.auth.permissions import require_permission
from src.database.models import Songs
from src.jobs.queue import QUEUE_HEAVY, submit_job
from src.jobs.tasks_dedup import dedup_backfill_pending
from src.schemas.dedup import (
    BackfillIn,
    BulkResolveIn,
    BulkResolveOut,
    DuplicateCandidateDetailOut,
    DuplicateListResponse,
    PromoteIn,
    RecordingOut,
    ResolveIn,
)
from src.schemas.jobs import JobOut
from src.schemas.users import UserOutSchema
from src.security import audit
from src.security.ratelimit import rate_limit
from src.services import dedup as dedup_service
from src.utils.pagination import decode_cursor, encode_cursor

router = APIRouter()

BULK_LIMIT = 100


def _utcnow():
    return datetime.now(timezone.utc)


@router.get("/admin/duplicates", response_model=DuplicateListResponse)
async def list_duplicates(
    status: str = Query(
        "pending",
        description="pending | proposed | auto_resolved | confirmed | rejected",
    ),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> DuplicateListResponse:
    """The duplicates review queue, keyset-paginated newest first."""
    last_id = None
    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != "id" or token["o"] != "desc" or len(token["k"]) != 2:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        try:
            last_id = int(token["k"][1])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid cursor")
    rows, items = await dedup_crud.list_candidates(status, last_id, limit)
    next_cursor = None
    if len(rows) == limit:
        next_cursor = encode_cursor("id", "desc", [rows[-1].id, rows[-1].id])
    return DuplicateListResponse(items=items, next_cursor=next_cursor)


@router.get(
    "/admin/duplicates/{candidate_id}", response_model=DuplicateCandidateDetailOut
)
async def get_duplicate(
    candidate_id: int,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> DuplicateCandidateDetailOut:
    """One candidate with the full pair embeds and resolution record."""
    _row, data = await dedup_crud.get_candidate(candidate_id)
    return DuplicateCandidateDetailOut(**data)


async def _resolve_one(row, action, winner_song_id, actor, request):
    """
    Apply one resolution. Raises 409/422 on bad state/input; the bulk route
    catches those into its skipped list.
    """
    if row.status not in ("pending", "proposed"):
        raise HTTPException(status_code=409, detail="Candidate already resolved")
    if action == "not_duplicate":
        row.status = "rejected"
        row.resolution = {"action": "not_duplicate"}
        row.resolved_by_id = getattr(actor, "id", None)
        row.resolved_at = _utcnow()
        await row.save()
        await audit.audit_event(
            audit.DEDUP_REVIEWED,
            request=request,
            actor=actor,
            target_type="duplicate",
            target_id=row.id,
            detail={"action": "not_duplicate", "layer": row.layer},
        )
        return row
    winner_id = winner_song_id or row.suggested_winner_id
    if winner_id not in (row.song_a_id, row.song_b_id):
        raise HTTPException(
            status_code=422,
            detail="winner_song_id must be one of the candidate pair",
        )
    song_a = await Songs.get_or_none(id=row.song_a_id)
    song_b = await Songs.get_or_none(id=row.song_b_id)
    if song_a is None or song_b is None:
        raise HTTPException(status_code=409, detail="A song of the pair was deleted")
    winner = song_a if winner_id == song_a.id else song_b
    await dedup_service.resolve_pair(
        song_a,
        song_b,
        winner,
        actor=actor,
        auto=False,
        request=request,
        candidate=row,
        detail={"layer": row.layer, "confidence": row.confidence},
    )
    return row


@router.post(
    "/admin/duplicates/{candidate_id}/resolve",
    response_model=DuplicateCandidateDetailOut,
)
async def resolve_duplicate(
    candidate_id: int,
    payload: ResolveIn,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> DuplicateCandidateDetailOut:
    """
    Resolve one candidate: merge keeps the winner as the canonical version
    and supersedes the loser (DB only -- no file is ever moved or deleted);
    not_duplicate rejects the pair forever.
    """
    if payload.action not in ("merge", "not_duplicate"):
        raise HTTPException(
            status_code=422, detail="action must be 'merge' or 'not_duplicate'"
        )
    row, _data = await dedup_crud.get_candidate(candidate_id)
    await _resolve_one(
        row, payload.action, payload.winner_song_id, current_user, request
    )
    _row, data = await dedup_crud.get_candidate(candidate_id)
    return DuplicateCandidateDetailOut(**data)


@router.post("/admin/duplicates/bulk-resolve", response_model=BulkResolveOut)
async def bulk_resolve_duplicates(
    payload: BulkResolveIn,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> BulkResolveOut:
    """Resolve up to 100 candidates in one call (accept suggested winners
    or reject); already-resolved ids are skipped with a reason."""
    if payload.action not in ("accept_suggested", "not_duplicate"):
        raise HTTPException(
            status_code=422,
            detail="action must be 'accept_suggested' or 'not_duplicate'",
        )
    if not payload.ids or len(payload.ids) > BULK_LIMIT:
        raise HTTPException(
            status_code=422,
            detail="ids must contain between 1 and {} entries".format(BULK_LIMIT),
        )
    resolved = 0
    skipped = []
    for candidate_id in payload.ids:
        try:
            row, _data = await dedup_crud.get_candidate(candidate_id)
            action = (
                "merge" if payload.action == "accept_suggested" else "not_duplicate"
            )
            if action == "merge" and not row.suggested_winner_id:
                skipped.append({"id": candidate_id, "reason": "No suggested winner"})
                continue
            await _resolve_one(row, action, None, current_user, request)
            resolved += 1
        except HTTPException as error:
            skipped.append({"id": candidate_id, "reason": error.detail})
    return BulkResolveOut(resolved=resolved, skipped=skipped)


@router.get("/admin/recordings/{recording_id}", response_model=RecordingOut)
async def get_recording(
    recording_id: int,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> RecordingOut:
    """A recording's identity, external IDs, version history, and related
    cuts (the extended/radio siblings)."""
    _rec, data = await dedup_crud.get_recording(recording_id)
    return RecordingOut(**data)


@router.post("/admin/recordings/{recording_id}/promote", response_model=RecordingOut)
async def promote_version(
    recording_id: int,
    payload: PromoteIn,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> RecordingOut:
    """
    One-click promote/restore: make the given version (superseded and
    quarantined ones included) the canonical one, demoting the current
    canonical. This is the reversibility guarantee -- every dedup decision
    can be undone here.
    """
    rec, _data = await dedup_crud.get_recording(recording_id)
    target = await Songs.get_or_none(id=payload.song_id, recording_id=rec.id)
    if target is None:
        raise HTTPException(
            status_code=422, detail="song_id must be a version of this recording"
        )
    demoted_ids = (
        await Songs.filter(recording_id=rec.id, version_status="canonical")
        .exclude(id=target.id)
        .values_list("id", flat=True)
    )
    await Songs.filter(id__in=list(demoted_ids)).update(version_status="superseded")
    target.version_status = "canonical"
    await target.save(update_fields=["version_status", "modified_at"])
    rec.canonical_song_id = target.id
    rec.duration_seconds = target.duration_seconds
    await rec.save(
        update_fields=["canonical_song_id", "duration_seconds", "modified_at"]
    )
    await dedup_service.sync_search([target.id] + list(demoted_ids))
    await audit.audit_event(
        audit.DEDUP_PROMOTED,
        request=request,
        actor=current_user,
        target_type="recording",
        target_id=rec.id,
        detail={"song_id": target.id, "demoted": list(demoted_ids)},
    )
    _rec, data = await dedup_crud.get_recording(recording_id)
    return RecordingOut(**data)


@router.post("/admin/duplicates/backfill", response_model=JobOut, status_code=202)
async def start_backfill(
    request: Request,
    payload: Optional[BackfillIn] = None,
    current_user: UserOutSchema = Depends(require_permission("site_settings")),
) -> JobOut:
    """
    Enqueue the retro-dedup walker over the whole library (MOO-90). Dry-run
    (the default) writes proposed candidates only -- a human-reviewable
    report, zero changes; the real run auto-resolves certain/confident
    pairs. 409 while one is queued/running; rate limited and audited.
    """
    payload = payload or BackfillIn()
    await rate_limit(
        "dedup_backfill", str(current_user.id), limit=3, window_seconds=300
    )
    if await dedup_backfill_pending():
        raise HTTPException(
            status_code=409,
            detail="A dedup backfill is already queued or running",
        )
    await audit.audit_event(
        audit.DEDUP_BACKFILL_STARTED,
        request=request,
        actor=current_user,
        target_type="dedup",
        detail={"dry_run": payload.dry_run},
    )
    return await submit_job(
        "dedup_backfill",
        payload={"dry_run": payload.dry_run},
        user_id=current_user.id,
        queue=QUEUE_HEAVY,
    )
