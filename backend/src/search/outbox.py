"""
The write side of the transactional search outbox (MOO-79).

Writers record song-affecting changes as plain PostgreSQL inserts -- never an
ES call, never an exception to the caller -- and nudge the drain. ES being
down (or Redis being down) can therefore never fail or slow a write path; the
outbox rows persist and the 30s worker cron catches up (D1).
"""
import logging
import os

from src.database.models import SearchOutbox
from src.search.es import es_enabled

logger = logging.getLogger("orp.search")

_BATCH = 1000

# Fixed arq job id so concurrent nudges collapse into one pending drain. The
# worker registers the function with keep_result=0, so the id frees up as
# soon as a drain finishes.
DRAIN_JOB_ID = "search:drain"


def _chunks(values, size=_BATCH):
    for start in range(0, len(values), size):
        end = start + size
        yield values[start:end]


async def enqueue_song_upsert(song_id):
    """Record that a song was created/changed. Never raises."""
    await enqueue_many([song_id], "upsert")


async def enqueue_song_delete(song_id):
    """Record that a song was deleted. Never raises."""
    await enqueue_many([song_id], "delete")


async def enqueue_many(song_ids, op):
    """Bulk-record outbox rows (batched inserts). Never raises."""
    if not song_ids or not es_enabled():
        return
    try:
        for chunk in _chunks(list(song_ids)):
            await SearchOutbox.bulk_create(
                [SearchOutbox(song_id=song_id, op=op) for song_id in chunk]
            )
    except Exception:
        logger.exception("search outbox enqueue failed (op=%s)", op)


async def nudge_drain():
    """
    Kick the outbox drain after a write batch. Workers enabled: enqueue the
    arq drain job (deduped by DRAIN_JOB_ID). Inline mode: drain in-process.
    Either way failures are swallowed -- the worker cron is the safety net.
    """
    if not es_enabled():
        return
    from src.jobs.queue import workers_enabled

    if workers_enabled():
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
            try:
                await pool.enqueue_job(
                    "search_drain_outbox",
                    _queue_name="orp:default",
                    _job_id=DRAIN_JOB_ID,
                )
            finally:
                await pool.close()
        except Exception:
            logger.exception("search drain nudge failed; cron will catch up")
    else:
        from src.search.indexer import drain_outbox

        try:
            await drain_outbox()
        except Exception:
            logger.exception("inline search drain failed; rows stay queued")
