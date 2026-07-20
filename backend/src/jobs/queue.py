"""
Job submission (MOO-77).

Every background job is a row in the jobs table (Postgres = source of truth);
Redis/arq is transport only. With WORKERS_ENABLED=false (the default, and the
single-image + test-harness mode) submit_job() executes the task in-process
before returning, so the returned job is already terminal — same response
envelope, no Redis required.

arq requires Python 3.8+ and is not installed in every environment, so it is
imported lazily here — request-path modules must never import arq at module
level (only src/worker.py, which the app never imports, may).
"""
import os

from src.database.models import Jobs
from src.jobs import (
    tasks,
    tasks_analysis,
    tasks_dedup,
    tasks_enrichment,
    tasks_export,
    tasks_follows,
)
from src.jobs.instrumented import instrumented

QUEUE_DEFAULT = "orp:default"
QUEUE_HEAVY = "orp:heavy"

# The task registry: job kind -> coroutine(ctx, job_id). Downstream stages
# register their kinds here (and in src/worker.py / src/worker_heavy.py for
# the async path). Inline mode calls straight through this dict, so the
# telemetry wrapper (MOO-83) is applied to the whole registry below.
_TASKS = {
    "scan_library": tasks.scan_library,
    "search_reindex": tasks.search_reindex,
    "analyze_track": tasks_analysis.analyze_track,
    "analyze_library": tasks_analysis.analyze_library,
    "dedup_song": tasks_dedup.dedup_song,
    "dedup_backfill": tasks_dedup.dedup_backfill,
    "fetch_track": tasks.fetch_track,
    # Beatport metadata enrichment (MOO-85), all on orp:heavy.
    "enrich_song": tasks_enrichment.enrich_song,
    "enrich_library": tasks_enrichment.enrich_library,
    "enrichment_manual_search": tasks_enrichment.enrichment_manual_search,
    # Artist follows / release tracking (MOO-80), network-light -> orp:default.
    "poll_release_sources": tasks_follows.poll_release_sources,
    "sync_artists_from_library": tasks_follows.sync_artists_from_library,
    # USB-ready DJ bundle export (MOO-86): IO-bound, on orp:default.
    "export_crate": tasks_export.export_crate,
}

TASKS = {kind: instrumented(task) for kind, task in _TASKS.items()}


def workers_enabled():
    """Whether jobs go to the arq worker tier (else they run inline)."""
    return os.environ.get("WORKERS_ENABLED", "").lower() in ("true", "1")


async def submit_job(
    kind, payload=None, user_id=None, queue=QUEUE_DEFAULT, arq_job_id=None
):
    """
    Create the jobs row and either enqueue it on arq (async mode) or run it
    in-process (inline mode). Returns the (refreshed) jobs row.

    [arq_job_id] (MOO-87) pins the arq job id so concurrent enqueues of the
    same logical work collapse into one pending job; when arq reports the
    dedup (enqueue_job -> None) the fresh jobs row is marked cancelled so it
    can never sit queued forever. Callers using this must register their
    task with keep_result=0, or the id stays blocked after completion.
    """
    job = await Jobs.create(
        kind=kind,
        payload=payload or {},
        queue=queue,
        created_by_id=user_id,
        arq_job_id=arq_job_id,
    )
    if workers_enabled():
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
        try:
            arq_job = await pool.enqueue_job(
                kind, job.id, _queue_name=queue, _job_id=arq_job_id
            )
            if arq_job is not None:
                job.arq_job_id = arq_job.job_id
                await job.save(update_fields=["arq_job_id"])
            elif arq_job_id is not None:
                job.status = "cancelled"
                job.error = "Deduplicated: an identical job is already queued"
                await job.save(update_fields=["status", "error"])
        finally:
            await pool.close()
    else:
        await TASKS[kind]({}, job.id)
        job = await Jobs.get(id=job.id)
    return job
