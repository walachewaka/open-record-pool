"""
DJ bundle export tasks (MOO-86).

export_crate builds one crate's USB-ready ZIP; cleanup_exports is the TTL
sweep that keeps /library/export from growing forever. Same jobs-row
lifecycle as every other task (MOO-77): running -> succeeded/failed, errors
recorded on the row, never propagated to the transport.
"""
from datetime import datetime, timezone

from src.database.models import CrateTracks, Crates, Jobs
from src.export import bundle


def _utcnow():
    return datetime.now(timezone.utc)


async def export_crate(ctx, job_id):
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    # Opportunistic TTL sweep: keeps inline mode (no worker, no cron) from
    # accumulating expired bundles. Cheap -- one listdir.
    await cleanup_exports(ctx)
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    crate = await Crates.get_or_none(id=payload.get("crate_id"))
    if crate is None:
        job.status = "failed"
        job.error = "Crate {} no longer exists".format(payload.get("crate_id"))
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return

    async def progress(done, total):
        job.progress = min(done / total, 1.0)
        await job.save(update_fields=["progress"])

    track_count = await CrateTracks.filter(crate_id=crate.id).count()
    try:
        result = await bundle.build_bundle(
            job,
            crate,
            payload.get("format"),
            payload.get("volume_label", bundle.DEFAULT_VOLUME_LABEL),
            payload.get("rekordbox_root", "/Volumes/ORP_USB"),
            progress_cb=progress,
            track_count=track_count,
        )
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


async def cleanup_exports(ctx):
    """
    Delete expired bundles and orphaned staging dirs. Cron'd every 30 min on
    the worker; inline mode calls it opportunistically at submit time. Never
    raises -- a failed sweep must not fail anything else.
    """
    try:
        return bundle.cleanup_expired()
    except Exception as error:
        print("[export] cleanup sweep failed: {}".format(error))
        return {"error": str(error)}
