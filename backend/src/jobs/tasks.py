"""
Background job task bodies (MOO-77).

Every task takes (ctx, job_id) — the arq calling convention — loads its jobs
row, and records its own lifecycle (running/succeeded/failed) on that row.
Postgres is the source of truth for job state; exceptions are recorded on the
row and swallowed, never propagated to the transport.
"""
from datetime import datetime, timezone

import src.crud.settings as settings_crud
import src.crud.songs as songs_crud
from src.database.models import Jobs


def _utcnow():
    return datetime.now(timezone.utc)


async def scan_pending():
    """Whether a library scan is already queued or running (409 guard)."""
    return await Jobs.filter(
        kind="scan_library", status__in=["queued", "running"]
    ).exists()


async def scan_library(ctx, job_id):
    """
    Scan the music volume and synchronize the songs table with it. The result
    is exactly the old ExtractionResult shape; the last-scan summary lands in
    the instance settings for the dashboard health panel.
    """
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    async def progress(files_done, files_total_estimate):
        if files_total_estimate > 0:
            job.progress = min(files_done / files_total_estimate, 1.0)
            await job.save(update_fields=["progress"])

    try:
        result = await songs_crud.sync_songs_from_disk(progress_cb=progress)
    except Exception as error:
        job.status = "failed"
        job.error = str(error)
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return
    job.status = "succeeded"
    job.result = result
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(update_fields=["status", "result", "progress", "finished_at"])
    await settings_crud.record_scan(result)

    # Refresh the artists table (MOO-80) so a rescan's new/renamed artists
    # are followable immediately. Best-effort: never fails the scan job.
    try:
        from src.crud.follows import sync_artists_impl

        await sync_artists_impl()
    except Exception as error:
        print("[follows] post-scan artist sync failed: {}".format(error))


async def fetch_track(ctx, job_id):
    """
    Acquire one track through a download provider (MOO-78). Runs on the heavy
    tier. The download_requests row is the domain object; this jobs row is the
    operational record. The pipeline advances both rows through their
    lifecycles and records the terminal state; we only guard the entry and any
    truly unexpected error. Adapters are imported lazily here (never in the
    request path).
    """
    from src.database.models import DownloadRequests
    from src.downloads import pipeline

    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    request_id = (job.payload or {}).get("request_id")
    request = await DownloadRequests.get_or_none(id=request_id)
    if request is None:
        job.status = "failed"
        job.error = "download_requests row {} missing".format(request_id)
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return
    if request.job_id is None:
        request.job_id = job.id
        await request.save(update_fields=["job_id"])
    try:
        await pipeline.run_fetch(job, request)
    except Exception as error:  # pragma: no cover - pipeline handles its own
        job.status = "failed"
        job.error = str(error).replace("\x00", "")
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])


async def search_drain_outbox(ctx):
    """
    Drain the search outbox into ES (MOO-79). Nudged after write batches
    (deduped by the fixed arq job id) and run by the worker cron every 30s
    as the safety net. Failures stay on the outbox rows; never raises.
    """
    from src.search.indexer import drain_outbox

    try:
        return await drain_outbox()
    except Exception as error:
        print("[search] outbox drain failed: {}".format(error))
        return {"processed": 0, "error": str(error)}


async def search_drain_outbox_cron(ctx):
    """The 30s cron wrapper (a distinct name keeps arq's registry unique)."""
    return await search_drain_outbox(ctx)


async def sync_song_requests_cron(ctx):
    """
    The 60s song-request read-repair sweep (MOO-81 D3.4): flips any
    `downloading` request to fulfilled/failed once its linked MOO-78 download
    lands, independent of any page being open. Never raises.
    """
    from src.crud.song_requests import sync_requests_from_downloads

    try:
        await sync_requests_from_downloads()
    except Exception as error:
        print("[song_requests] sync failed: {}".format(error))


async def search_reindex(ctx, job_id):
    """
    Zero-downtime full search reindex (MOO-79): build the next versioned
    index from PostgreSQL, replay drift, swap the orp-tracks alias. Standard
    jobs-row lifecycle like scan_library.
    """
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    from src.search.reindex import run_reindex

    try:
        result = await run_reindex()
    except Exception as error:
        job.status = "failed"
        job.error = str(error)
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return
    job.status = "succeeded"
    job.result = result
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(update_fields=["status", "result", "progress", "finished_at"])
