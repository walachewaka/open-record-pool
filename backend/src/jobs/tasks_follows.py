"""
Background job task bodies for artist follows / release tracking (MOO-80).
Same conventions as src/jobs/tasks.py / tasks_enrichment.py: every task takes
(ctx, job_id), records its lifecycle on the jobs row, and never propagates
exceptions to the transport.
"""
from datetime import datetime, timezone

from src.database.models import Jobs


def _utcnow():
    return datetime.now(timezone.utc)


async def poll_release_sources(ctx, job_id):
    """The D4 poll tick, on orp:default (network-light: cached HTTP + a
    per-artist politeness sleep, no CPU/ffmpeg work -- doesn't belong on
    orp:heavy)."""
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    from src.crud.follows import poll_impl

    try:
        result = await poll_impl()
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


async def sync_artists_from_library(ctx, job_id):
    """Materializes/refreshes the artists table from published library
    tracks (also invoked directly, not via a job row, as the last step of a
    successful scan_library)."""
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    from src.crud.follows import sync_artists_impl

    try:
        result = await sync_artists_impl()
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


async def poll_release_sources_pending():
    """Whether a poll is already queued/running (409 guard for the manual
    admin trigger)."""
    return await Jobs.filter(
        kind="poll_release_sources", status__in=["queued", "running"]
    ).exists()


async def poll_release_sources_cron(ctx):
    """The 15-min cron tick (D4): submits a jobs row (inline when
    WORKERS_ENABLED=false, else enqueued on orp:default) unless one is
    already queued/running -- a distinct name keeps arq's registry unique
    from the (ctx, job_id) task above."""
    if await poll_release_sources_pending():
        return
    from src.jobs.queue import submit_job

    await submit_job("poll_release_sources")


async def sync_artists_from_library_cron(ctx):
    """The hourly cron tick (D4)."""
    from src.jobs.queue import submit_job

    await submit_job("sync_artists_from_library")
