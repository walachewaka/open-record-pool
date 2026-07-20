"""
The arq worker entry point (MOO-77): `arq src.worker.WorkerSettings`.

This module is the ONLY place allowed to import arq at module level — the
FastAPI app never imports it (arq requires Python 3.8+ and is absent from the
inline-mode environments). It consumes the orp:default queue; MOO-87 adds a
worker-heavy service on orp:heavy later.
"""
import os

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func
from tortoise import Tortoise

from src.database.config import TORTOISE_ORM
from src.jobs.instrumented import instrumented
from src.jobs.tasks import (
    scan_library,
    search_drain_outbox,
    search_drain_outbox_cron,
    search_reindex,
    sync_song_requests_cron,
)
from src.jobs.tasks_analysis import analyze_library
from src.jobs.tasks_export import cleanup_exports, export_crate
from src.jobs.tasks_follows import (
    poll_release_sources,
    poll_release_sources_cron,
    sync_artists_from_library,
    sync_artists_from_library_cron,
)
from src.telemetry.shipper import ship_audit_events


async def startup(ctx):
    # Schema management is the backend entrypoint's job (aerich); the worker
    # only connects. compose depends_on ordering plus arq retries cover the
    # startup window on a fresh database.
    await Tortoise.init(config=TORTOISE_ORM)
    # Search bootstrap (MOO-79): tolerate ES still coming up; the cron drain
    # and the next boot retry.
    from src.search.indexer import ensure_search_index

    await ensure_search_index()

    # Telemetry (MOO-83): this process owns its own event buffer, so it needs
    # its own flush loop -- job.finished is emitted from here, not the API.
    from src.telemetry import start_emitter

    start_emitter()


async def shutdown(ctx):
    from src.search.es import close_es
    from src.telemetry import stop_emitter

    await stop_emitter()
    await close_es()
    await Tortoise.close_connections()


class WorkerSettings:
    functions = [
        # instrumented(...) emits job.finished for the terminal state each task
        # records (MOO-83); functools.wraps keeps the arq registry name.
        instrumented(scan_library),
        # keep_result=0 frees the fixed "search:drain" job id the moment a
        # drain finishes, so the next write batch can nudge again (MOO-79).
        func(search_drain_outbox, keep_result=0),
        instrumented(search_reindex),
        # The analyzer backfill walker (MOO-87). analyze_track itself lives
        # on orp:heavy, consumed by src/worker_heavy.py -- not here.
        instrumented(analyze_library),
        # Artist follows / release tracking (MOO-80): network-light (cached
        # HTTP via MOO-85's client), so they share this tier, not orp:heavy.
        instrumented(poll_release_sources),
        instrumented(sync_artists_from_library),
        # DJ bundle export (MOO-86): copies + zips GBs of audio, so it gets the
        # long job_timeout this tier already has.
        instrumented(export_crate),
    ]
    # Safety-net drain every 30s: outbox rows survive ES/Redis outages and
    # this catches up whatever the write-path nudges missed (MOO-79).
    cron_jobs = [
        cron(search_drain_outbox_cron, second={0, 30}, keep_result=0),
        # Song request fulfillment read-repair every 60s (MOO-81 D3.4): keeps
        # badges/statuses fresh even with no page open.
        cron(sync_song_requests_cron, second=0, keep_result=0),
        # Release poll tick every 15 min + hourly artist re-sync (MOO-80 D4).
        cron(poll_release_sources_cron, minute={0, 15, 30, 45}, keep_result=0),
        cron(sync_artists_from_library_cron, minute={5}, keep_result=0),
        # Export artifact GC every 30 min (MOO-86): bundles past EXPORT_TTL_HOURS
        # and staging dirs a crashed worker left behind.
        cron(cleanup_exports, minute={0, 30}, keep_result=0),
        # Audit log -> ES projection every 60s (MOO-83 D4). Postgres stays
        # authoritative; this is the dashboards' copy. Idempotent by doc id.
        cron(ship_audit_events, second=0, keep_result=0),
    ]
    queue_name = "orp:default"
    max_jobs = int(os.environ.get("WORKER_CONCURRENCY", "10"))
    job_timeout = 3600
    keep_result = 3600
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://redis:6379/0")
    )
    on_startup = startup
    on_shutdown = shutdown
