"""
The dedup job bodies (MOO-90): dedup_song (the per-track pipeline stage on
orp:heavy, enqueued when MOO-87 analysis completes) and dedup_backfill (the
throttled retro-dedup walker with a dry-run mode). Same conventions as
src/jobs/tasks.py: every task takes (ctx, job_id), records its lifecycle on
the jobs row, and never propagates exceptions to the transport.
"""
from datetime import datetime, timezone

from src.database.models import Jobs, Songs
from src.security import audit
from src.services import dedup as dedup_service

_BATCH = 500


def _utcnow():
    return datetime.now(timezone.utc)


async def dedup_song(ctx, job_id):
    """The dedup pipeline stage for one song (D3), after analysis."""
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    try:
        song = await Songs.get_or_none(id=payload.get("song_id"))
        if song is None:
            result = {"song_id": payload.get("song_id"), "skipped": "song deleted"}
        else:
            result = await dedup_service.process_song(song)
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


async def dedup_backfill_pending():
    """Whether a dedup backfill is already queued or running (409 guard)."""
    return await Jobs.filter(
        kind="dedup_backfill", status__in=["queued", "running"]
    ).exists()


async def dedup_backfill(ctx, job_id):
    """
    The retro-dedup walker (MOO-90): keyset-iterate every song, ensure the
    norm/ngram indexes, and run the match cascade. dry_run=true records
    proposed candidates only -- the human-reviewable report is the proposed
    list in the admin UI -- and changes nothing else. The real run
    auto-resolves certain/confident pairs per D3. Idempotent: pairs already
    recorded in duplicate_candidates are never re-raised.
    """
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    dry_run = bool(payload.get("dry_run", True))
    cfg = await dedup_service.load_config()

    totals = {
        "songs_scanned": 0,
        "certain": 0,
        "confident": 0,
        "borderline": 0,
        "related_cuts": 0,
        "auto_resolved": 0,
        "proposed": 0,
        "pending": 0,
        "dry_run": dry_run,
    }
    total = await Songs.all().count()
    last_id = 0
    try:
        while True:
            batch = await Songs.filter(id__gt=last_id).order_by("id").limit(_BATCH)
            if not batch:
                break
            for song in batch:
                summary = await dedup_service.process_song(
                    song, cfg=cfg, dry_run=dry_run
                )
                totals["songs_scanned"] += 1
                for key in (
                    "certain",
                    "confident",
                    "borderline",
                    "related_cuts",
                    "auto_resolved",
                    "proposed",
                    "pending",
                ):
                    totals[key] += summary[key]
            last_id = batch[-1].id
            if total:
                job.progress = min(totals["songs_scanned"] / total, 1.0)
                await job.save(update_fields=["progress"])
    except Exception as error:
        job.status = "failed"
        job.error = str(error).replace("\x00", "")
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return

    job.status = "succeeded"
    job.result = totals
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(update_fields=["status", "result", "progress", "finished_at"])
    await audit.audit_event(
        audit.DEDUP_BACKFILL_FINISHED,
        target_type="dedup",
        target_id=job.id,
        detail=totals,
    )
