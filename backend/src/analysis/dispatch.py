"""
The analyzer dispatch seam (MOO-87 D3): ensure_analysis_row records pass-1
facts, enqueue_analysis queues pass 2 on orp:heavy. enqueue_analysis is the
ONE public entry point every ingestion path uses -- the /music scan, admin
uploads, the backfill job, and later the MOO-78 download engine.
"""
from datetime import datetime, timezone

from tortoise.exceptions import IntegrityError

from src.analysis.versions import FIELD_VERSIONS
from src.database.models import Jobs, TrackAnalysis

# arq job id per song: concurrent enqueues of the same track collapse into
# one pending job (redundant with the jobs-table dedup below, but it also
# holds across API replicas racing between the check and the insert).
ARQ_JOB_PREFIX = "analyze_track:"


def _utcnow():
    return datetime.now(timezone.utc)


async def ensure_analysis_row(song_id, technical=None):
    """
    Upsert the track_analysis row for a song. With a [technical] dict (the
    pass-1 output of src.analysis.technical.extract_technical) the pass-1
    columns are written and pass1_status flips to succeeded -- the track is
    fully usable before pass 2 ever runs (tiered passes, D3).
    """
    row = await TrackAnalysis.get_or_none(song_id=song_id)
    if row is None:
        try:
            row = await TrackAnalysis.create(song_id=song_id)
        except IntegrityError:  # lost a concurrent-create race
            row = await TrackAnalysis.get(song_id=song_id)
    if technical is not None:
        for field, value in technical.items():
            setattr(row, field, value)
        versions = dict(row.field_versions or {})
        versions["technical"] = FIELD_VERSIONS["technical"]
        row.field_versions = versions
        row.pass1_status = "succeeded"
        row.pass1_at = _utcnow()
        await row.save()
    return row


async def enqueue_analysis(song_id, force=False, fields=None, user_id=None):
    """
    Enqueue the analyze_track pass-2 job for one song on orp:heavy. Deduped:
    when an analyze_track job for this song is already queued or running,
    returns None instead of creating a second one. Returns the jobs row
    otherwise (terminal already in inline mode). The task itself re-checks
    checksum + field versions, so a redundant enqueue is always harmless.
    """
    from src.jobs.queue import QUEUE_HEAVY, submit_job

    arq_job_id = ARQ_JOB_PREFIX + str(song_id)
    already = await Jobs.filter(
        kind="analyze_track",
        arq_job_id=arq_job_id,
        status__in=["queued", "running"],
    ).exists()
    if already:
        return None
    payload = {"song_id": song_id, "force": bool(force)}
    if fields:
        payload["fields"] = list(fields)
    return await submit_job(
        "analyze_track",
        payload=payload,
        user_id=user_id,
        queue=QUEUE_HEAVY,
        arq_job_id=arq_job_id,
    )
