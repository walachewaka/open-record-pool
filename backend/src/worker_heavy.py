"""
The CPU-heavy analyzer worker entry point (MOO-87):
`arq src.worker_heavy.WorkerSettings`, consuming orp:heavy.

Like src/worker.py, this module (and only worker entry points) may import
arq at module level. Concurrency scales with the host (D4): the env
override wins, else max(1, min(cpu_count - 1, 8)) -- a NAS runs 1-2 slots,
an 8-core box runs 7, monsters cap at 8 per container and scale OUT with
`docker compose up -d --scale worker-heavy=N` (workers are stateless queue
consumers). Each slot stays one-threaded: ffmpeg runs -threads 1 and the
service sets OMP_NUM_THREADS=1 / NUMBA_NUM_THREADS=1, so concurrency is
governed here, not by thread explosion.
"""
import os

from arq.connections import RedisSettings
from arq.worker import func
from tortoise import Tortoise

from src.database.config import TORTOISE_ORM
from src.jobs.instrumented import instrumented
from src.jobs.tasks import fetch_track
from src.jobs.tasks_analysis import analyze_track
from src.jobs.tasks_dedup import dedup_backfill, dedup_song
from src.jobs.tasks_enrichment import (
    enrich_library,
    enrich_song,
    enrichment_manual_search,
)


def heavy_concurrency():
    """
    The worker slot count (D4), logged at startup so the scaling behavior
    is observable: WORKER_HEAVY_CONCURRENCY when set, else derived from the
    host CPU count.
    """
    cpu_count = os.cpu_count() or 2
    env = os.environ.get("WORKER_HEAVY_CONCURRENCY")
    if env:
        value = max(1, int(env))
        print(
            "[worker-heavy] concurrency={} (cpu_count={}, env set)".format(
                value, cpu_count
            ),
            flush=True,  # container stdout is block-buffered
        )
        return value
    value = max(1, min(cpu_count - 1, 8))
    print(
        "[worker-heavy] concurrency={} (cpu_count={}, env unset)".format(
            value, cpu_count
        ),
        flush=True,
    )
    return value


async def startup(ctx):
    # ANALYZER_NICE (D4): deprioritize analysis below the API/DB. Applied
    # process-wide, inherited by every child ffmpeg/fpcalc subprocess.
    nice = int(os.environ.get("ANALYZER_NICE", "10"))
    if nice and hasattr(os, "nice"):
        try:
            os.nice(nice)
        except OSError as error:
            print("[worker-heavy] os.nice({}) failed: {}".format(nice, error))
    # Schema management is the backend entrypoint's job (aerich); the worker
    # only connects (same contract as src/worker.py).
    await Tortoise.init(config=TORTOISE_ORM)

    # Telemetry (MOO-83): own process, own event buffer, own flush loop.
    from src.telemetry import start_emitter

    start_emitter()


async def shutdown(ctx):
    from src.search.es import close_es
    from src.telemetry import stop_emitter

    await stop_emitter()
    await close_es()
    await Tortoise.close_connections()


class WorkerSettings:
    # keep_result=0: the fixed "analyze_track:<song_id>" / "dedup_song:<id>"
    # dedup ids must free the moment a run finishes, or a legitimate re-run
    # within the result TTL would be silently dropped by arq.
    # instrumented(...) wraps each task so its terminal jobs row emits the
    # job.finished telemetry event (MOO-83); wraps preserves the arq name.
    functions = [
        func(instrumented(analyze_track), keep_result=0, max_tries=3),
        # The MOO-90 dedup pipeline stage + retro-dedup walker share the
        # heavy tier: fingerprint comparisons are CPU work.
        func(instrumented(dedup_song), keep_result=0, max_tries=3),
        instrumented(dedup_backfill),
        # Music download engine (MOO-78): network fetch + convert + import.
        func(instrumented(fetch_track), keep_result=0, max_tries=3),
        # Beatport metadata enrichment (MOO-85): outbound API calls, so they
        # share the heavy tier (rate-limited/cached inside the client).
        func(instrumented(enrich_song), keep_result=0, max_tries=3),
        instrumented(enrich_library),
        func(instrumented(enrichment_manual_search), keep_result=0, max_tries=3),
    ]
    queue_name = "orp:heavy"
    max_jobs = heavy_concurrency()
    # Downloads can run to DOWNLOAD_TIMEOUT_SECONDS (default 900) plus post-
    # processing headroom; keep the arq job_timeout above the tool timeout.
    job_timeout = int(os.environ.get("DOWNLOAD_TIMEOUT_SECONDS", "900")) + 300
    max_tries = 3
    keep_result = 0
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://redis:6379/0")
    )
    on_startup = startup
    on_shutdown = shutdown
