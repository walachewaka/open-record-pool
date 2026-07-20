"""
Background job task bodies for Beatport enrichment (MOO-85): single-song
enrich, the resumable/budget-throttled library-wide backfill, and a
reviewer-driven manual re-search. Same conventions as src/jobs/tasks.py /
tasks_dedup.py: every task takes (ctx, job_id), records its lifecycle on the
jobs row, and never propagates exceptions to the transport.
"""
import asyncio
import os
from datetime import datetime, timezone

from src.database.models import Jobs, SongEnrichment, Songs
from src.enrichment import provider, scoring, service

_BATCH = 100


def _utcnow():
    return datetime.now(timezone.utc)


def _backfill_budget_per_hour():
    return int(os.environ.get("BEATPORT_BACKFILL_BUDGET_PER_HOUR", "3600"))


async def enrich_song_pending(song_id):
    """Whether a single-song enrich is already queued/running for [song_id]
    (409 guard). Checked in Python rather than a JSON containment query --
    the queued/running set is always tiny."""
    rows = await Jobs.filter(kind="enrich_song", status__in=["queued", "running"])
    return any((row.payload or {}).get("song_id") == song_id for row in rows)


async def enrichment_backfill_pending():
    """Whether a library backfill is already queued/running (409 guard)."""
    return await Jobs.filter(
        kind="enrich_library", status__in=["queued", "running"]
    ).exists()


async def enrich_song(ctx, job_id):
    """The single-song enrich pipeline stage (D7), on orp:heavy."""
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    song_id = payload.get("song_id")
    force = bool(payload.get("force", False))
    try:
        row = await service.enrich_song(song_id, force=force)
        result = {
            "song_id": song_id,
            "status": row.status,
            "confidence": row.confidence,
            "beatport_track_id": row.beatport_track_id,
        }
    except Exception as error:
        job.status = "failed"
        job.error = str(error).replace("\x00", "")
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return
    job.status = "succeeded"
    job.result = result
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(update_fields=["status", "result", "progress", "finished_at"])


async def enrich_library(ctx, job_id):
    """
    Resumable, budget-throttled library-wide backfill (D7): walks every song
    id ascending from the payload's cursor (default 0), enriching a song
    when it has no enrichment row yet, or its row's status is in
    payload["statuses"] (default: skip anything "applied"/"rejected" unless
    force). Persists {"cursor", "processed", ...} into the jobs row after
    every _BATCH-sized page so a killed/restarted run can resubmit with the
    recorded cursor and never reprocess already-applied rows. Sleeps between
    calls to keep the observed Beatport call rate under
    BEATPORT_BACKFILL_BUDGET_PER_HOUR calls/hour.
    """
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    cursor = int(payload.get("cursor") or 0)
    force = bool(payload.get("force", False))
    statuses = payload.get("statuses")
    budget_per_hour = _backfill_budget_per_hour()
    min_interval = 3600.0 / budget_per_hour if budget_per_hour > 0 else 0.0

    totals = {
        "processed": 0,
        "matched": 0,
        "applied": 0,
        "needs_review": 0,
        "no_match": 0,
        "api_calls": 0,
        "cursor": cursor,
    }
    try:
        client = provider.get_client()
    except Exception as error:
        job.status = "failed"
        job.error = str(error)
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return

    try:
        while True:
            batch = await Songs.filter(id__gt=cursor).order_by("id").limit(_BATCH)
            if not batch:
                break
            existing = {
                row.song_id: row
                for row in await SongEnrichment.filter(
                    song_id__in=[s.id for s in batch], provider="beatport"
                )
            }
            for song in batch:
                cursor = song.id
                row = existing.get(song.id)
                if row is not None and not force:
                    if statuses:
                        if row.status not in statuses:
                            continue
                    elif row.status in ("applied", "rejected"):
                        continue
                if min_interval:
                    await asyncio.sleep(min_interval)
                result_row = await service.enrich_song(
                    song.id, force=force, client=client
                )
                totals["api_calls"] += 1
                totals["processed"] += 1
                if result_row.status in ("applied", "needs_review"):
                    totals["matched"] += 1
                if result_row.status in totals:
                    totals[result_row.status] += 1
            totals["cursor"] = cursor
            job.result = dict(totals)
            await job.save(update_fields=["result"])
    except Exception as error:
        job.status = "failed"
        job.error = str(error).replace("\x00", "")
        job.result = dict(totals)
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "result", "finished_at"])
        return

    job.status = "succeeded"
    job.result = dict(totals)
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(update_fields=["status", "result", "progress", "finished_at"])


async def enrichment_manual_search(ctx, job_id):
    """
    Reviewer-driven re-search (D7): searches Beatport with the reviewer's
    query, re-scores against the song's current tags, and replaces the
    row's candidate list -- setting it back to needs_review (unless already
    applied) so the reviewer can pick from the fresh results.
    """
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    enrichment_id = payload.get("enrichment_id")
    query = payload.get("query") or ""
    try:
        row = await SongEnrichment.get_or_none(id=enrichment_id)
        if row is None:
            raise ValueError("enrichment row {} not found".format(enrichment_id))
        song = await Songs.get_or_none(id=row.song_id)
        client = provider.get_client()
        raw_candidates = await client.search_tracks(query)
        fields = service.song_fields(song) if song else {}
        ranked = scoring.rank_candidates(fields, raw_candidates)
        row.candidates = ranked
        best = ranked[0] if ranked else None
        row.confidence = best["score"] if best else None
        if best is not None:
            row.beatport_track_id = best["beatport_track_id"]
        if row.status != "applied":
            row.status = "needs_review" if ranked else "no_match"
        row.matched_at = _utcnow()
        await row.save()
        result = {"enrichment_id": enrichment_id, "candidates": len(ranked)}
    except Exception as error:
        job.status = "failed"
        job.error = str(error).replace("\x00", "")
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return
    job.status = "succeeded"
    job.result = result
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(update_fields=["status", "result", "progress", "finished_at"])
