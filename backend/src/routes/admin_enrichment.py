"""
Admin Beatport enrichment API (MOO-85): provider status, trigger a single
song enrich / library backfill / manual re-search (all 202 job envelopes --
MOO-77 D2, the actual Beatport call always happens inside a worker job,
never here), the review queue, per-song detail (the MOO-82 consumption
contract), and accept/reject/un-apply. Reuses `edit_metadata` -- the same
permission that already gates DB-side metadata edits (no new permission key
or matrix row).

Security bar (MOO-89 / SECURITY.md): every route declares its guard (item
1); the trigger endpoints are rate limited (item 5); apply/reject/un-apply
are audited (item 6); the outbound allowlist/redirect/artwork-host checks
live in src/enrichment/beatport_client.py (item 9).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import src.crud.enrichment as enrichment_crud
from src.auth.permissions import require_permission
from src.database.models import Songs, SongEnrichment
from src.enrichment import provider, service
from src.jobs.queue import QUEUE_HEAVY, submit_job
from src.jobs.tasks_enrichment import enrich_song_pending, enrichment_backfill_pending
from src.schemas.enrichment import (
    AcceptIn,
    BackfillTriggerIn,
    EnrichmentListResponse,
    EnrichmentOut,
    EnrichTriggerIn,
    ManualSearchIn,
    ProviderStatusOut,
)
from src.schemas.jobs import JobOut
from src.schemas.users import UserOutSchema
from src.security import audit
from src.security.ratelimit import rate_limit

router = APIRouter(prefix="/admin/enrichment", tags=["admin: enrichment"])


def _disabled_error():
    return HTTPException(
        status_code=503,
        detail="Beatport integration is not configured "
        "(set BEATPORT_CLIENT_ID / BEATPORT_CLIENT_SECRET, or BEATPORT_MOCK=true)",
    )


async def _get_song_or_404(song_id):
    song = await Songs.get_or_none(id=song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


async def _get_row_or_404(enrichment_id):
    row = await SongEnrichment.get_or_none(id=enrichment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Enrichment row not found")
    return row


@router.get("/status", response_model=ProviderStatusOut)
async def get_status(
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> ProviderStatusOut:
    """Provider tri-state (mock/live/disabled) + counts. Never calls
    Beatport itself (MOO-77 D2)."""
    return ProviderStatusOut(**await provider.provider_status())


@router.post("/songs/{song_id}", response_model=JobOut, status_code=202)
async def trigger_enrich_song(
    song_id: int,
    payload: EnrichTriggerIn,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> JobOut:
    """Enqueue a single-song enrich; 202 job envelope (MOO-77)."""
    await rate_limit(
        "enrich_trigger", str(current_user.id), limit=30, window_seconds=60
    )
    mode, _reason = provider.mode_and_reason()
    if mode == "disabled":
        raise _disabled_error()
    await _get_song_or_404(song_id)
    if await enrich_song_pending(song_id):
        raise HTTPException(
            status_code=409,
            detail="Enrichment already queued or running for this song",
        )
    return await submit_job(
        "enrich_song",
        payload={"song_id": song_id, "force": payload.force},
        user_id=current_user.id,
        queue=QUEUE_HEAVY,
    )


@router.get("/songs/{song_id}", response_model=EnrichmentOut)
async def get_song_enrichment(
    song_id: int,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> EnrichmentOut:
    """
    The per-song enrichment row -- the stable contract MOO-82's ID3 editor
    consumes for its suggested-values panel and artwork candidates.
    """
    _row, data = await enrichment_crud.get_by_song(song_id)
    return EnrichmentOut(**data)


@router.post("/backfill", response_model=JobOut, status_code=202)
async def trigger_backfill(
    request: Request,
    payload: Optional[BackfillTriggerIn] = None,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> JobOut:
    """Enqueue the resumable, budget-throttled library-wide backfill."""
    payload = payload or BackfillTriggerIn()
    await rate_limit(
        "enrich_backfill", str(current_user.id), limit=3, window_seconds=3600
    )
    mode, _reason = provider.mode_and_reason()
    if mode == "disabled":
        raise _disabled_error()
    if await enrichment_backfill_pending():
        raise HTTPException(
            status_code=409,
            detail="A library enrichment backfill is already queued or running",
        )
    await audit.audit_event(
        "enrichment.backfill_started",
        request=request,
        actor=current_user,
        target_type="enrichment",
        detail={"cursor": payload.cursor, "force": payload.force},
    )
    return await submit_job(
        "enrich_library",
        payload={
            "cursor": payload.cursor,
            "force": payload.force,
            "statuses": payload.statuses,
        },
        user_id=current_user.id,
        queue=QUEUE_HEAVY,
    )


@router.get("/queue", response_model=EnrichmentListResponse)
async def get_queue(
    status: Optional[str] = Query("needs_review"),
    q: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> EnrichmentListResponse:
    """The review queue, keyset-paginated newest first."""
    items, next_cursor = await enrichment_crud.list_queue(
        status=status, q=q, cursor=cursor, limit=limit
    )
    return EnrichmentListResponse(items=items, next_cursor=next_cursor)


@router.post("/{enrichment_id}/accept", response_model=EnrichmentOut)
async def accept_candidate(
    enrichment_id: int,
    payload: AcceptIn,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> EnrichmentOut:
    """
    Accept a match and apply it: writes the chosen candidate's fields onto
    the song (skipping any manual-locked field), never calls Beatport --
    uses the candidate payload already stored from the last search/
    re-search. Unknown candidate id -> 422 (run manual search first, rather
    than silently fetching from Beatport inside a request handler).
    """
    row = await _get_row_or_404(enrichment_id)
    candidates = row.candidates or []
    if payload.beatport_track_id is not None:
        chosen = next(
            (
                c
                for c in candidates
                if c.get("beatport_track_id") == payload.beatport_track_id
            ),
            None,
        )
        if chosen is None:
            raise HTTPException(
                status_code=422, detail="Unknown candidate; run manual search first"
            )
    else:
        chosen = candidates[0] if candidates else None
        if chosen is None:
            raise HTTPException(status_code=422, detail="No candidate to accept")

    fields = (
        payload.fields if payload.fields is not None else list(service.APPLIED_FIELDS)
    )
    unknown_fields = [f for f in fields if f not in service.APPLIED_FIELDS]
    if unknown_fields:
        raise HTTPException(
            status_code=422,
            detail="Unknown field(s): {}".format(", ".join(unknown_fields)),
        )

    song = await _get_song_or_404(row.song_id)
    row.payload = service.build_payload(chosen.get("payload"), song)
    row.beatport_track_id = chosen.get("beatport_track_id")
    row.confidence = chosen.get("score")
    await row.save()
    await service.apply(
        row,
        fields=fields,
        user_id=current_user.id,
        method="manual",
        request=request,
        actor=current_user,
    )
    _row, data = await enrichment_crud.get_by_id(enrichment_id)
    return EnrichmentOut(**data)


@router.post("/{enrichment_id}/reject", response_model=EnrichmentOut)
async def reject_candidate(
    enrichment_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> EnrichmentOut:
    """Mark not-a-match; an already-applied row is un-applied first."""
    row = await _get_row_or_404(enrichment_id)
    await service.reject(
        row, user_id=current_user.id, request=request, actor=current_user
    )
    _row, data = await enrichment_crud.get_by_id(enrichment_id)
    return EnrichmentOut(**data)


@router.post("/{enrichment_id}/unapply", response_model=EnrichmentOut)
async def unapply_candidate(
    enrichment_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> EnrichmentOut:
    """Revert an applied match to its pre-apply snapshot and clear the
    beatport-owned locks."""
    row = await _get_row_or_404(enrichment_id)
    if row.status != "applied":
        raise HTTPException(status_code=409, detail="Not applied")
    await service.unapply(row, request=request, actor=current_user)
    _row, data = await enrichment_crud.get_by_id(enrichment_id)
    return EnrichmentOut(**data)


@router.post("/{enrichment_id}/manual-search", response_model=JobOut, status_code=202)
async def manual_search(
    enrichment_id: int,
    payload: ManualSearchIn,
    current_user: UserOutSchema = Depends(require_permission("edit_metadata")),
) -> JobOut:
    """Reviewer-driven re-search; 202 job envelope. On completion the row's
    candidates are replaced with the freshly scored results."""
    await rate_limit(
        "enrich_trigger", str(current_user.id), limit=30, window_seconds=60
    )
    mode, _reason = provider.mode_and_reason()
    if mode == "disabled":
        raise _disabled_error()
    await _get_row_or_404(enrichment_id)
    return await submit_job(
        "enrichment_manual_search",
        payload={"enrichment_id": enrichment_id, "query": payload.query},
        user_id=current_user.id,
        queue=QUEUE_HEAVY,
    )
