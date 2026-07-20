"""
Job telemetry wrapper (MOO-83).

Every task owns its own lifecycle bookkeeping (MOO-77), so there is no single
line where a job goes terminal. Rather than sprinkle an emit() through six task
modules -- and miss the seventh someone adds next month -- we wrap the task at
the ONE boundary both execution modes share: the callable that arq (async mode)
and submit_job (inline mode) invoke.

The wrapper re-reads the row after the task returns and emits job.finished for
whatever terminal state the task recorded. functools.wraps keeps __name__, which
is what arq registers the task under.
"""
import functools

from src.database.models import Jobs
from src.telemetry import events

TERMINAL = ("succeeded", "failed")


def instrumented(task):
    """Wrap a (ctx, job_id) task so its terminal state emits job.finished."""

    @functools.wraps(task)
    async def wrapper(ctx, job_id):
        try:
            return await task(ctx, job_id)
        finally:
            try:
                job = await Jobs.get_or_none(id=job_id)
                if job is not None and job.status in TERMINAL:
                    events.job_finished(job)
            except Exception:  # pragma: no cover - never break the job
                pass

    return wrapper
