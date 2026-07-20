"""
CRUD + serialization for download requests (MOO-78). Keyset-paginated list
queries (own / admin) and the cancel/retry state-machine guards. Mirrors the
MOO-77 pagination contract used by routes/jobs.py.
"""
from fastapi import HTTPException

from src.database.models import DownloadRequests
from src.downloads import service
from src.jobs.queue import QUEUE_HEAVY, submit_job
from src.schemas.downloads import DownloadRequestOut
from src.utils.pagination import decode_cursor, encode_cursor, keyset_filter

STATUSES = [
    "queued",
    "fetching",
    "postprocessing",
    "imported",
    "duplicate_skipped",
    "failed",
    "cancelled",
]


def serialize(request, include_metadata=False):
    """A DownloadRequestOut from a row whose `requested_by` is fetched."""
    username = None
    user = getattr(request, "requested_by", None)
    if user is not None and getattr(user, "id", None) is not None:
        username = user.username
    return DownloadRequestOut(
        id=request.id,
        provider=request.provider,
        url=request.url,
        external_id=request.external_id,
        status=request.status,
        origin=request.origin,
        origin_ref=request.origin_ref,
        priority=request.priority,
        progress=request.progress,
        attempts=request.attempts,
        error=request.error,
        error_kind=request.error_kind,
        requested_by_id=request.requested_by_id,
        requested_by_username=username,
        job_id=request.job_id,
        song_id=request.song_id,
        source_metadata=request.source_metadata if include_metadata else None,
        created_at=request.created_at,
        started_at=request.started_at,
        finished_at=request.finished_at,
    )


def _cursor_last_id(cursor):
    token = decode_cursor(cursor)
    if token["s"] != "id" or token["o"] != "desc":
        raise HTTPException(status_code=422, detail="Invalid cursor")
    try:
        return int(token["k"][-1])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid cursor")


async def _paginate(query, limit, cursor):
    if cursor:
        last_id = _cursor_last_id(cursor)
        query = query.filter(keyset_filter("id", "desc", last_id, last_id))
    rows = await query.order_by("-id").limit(limit).prefetch_related("requested_by")
    items = [serialize(row) for row in rows]
    next_cursor = None
    if len(items) == limit:
        next_cursor = encode_cursor("id", "desc", [items[-1].id, items[-1].id])
    return items, next_cursor


def _validate_status(status):
    if status is not None and status not in STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of: {}".format(", ".join(STATUSES)),
        )


async def list_mine(user_id, status=None, cursor=None, limit=50):
    _validate_status(status)
    query = DownloadRequests.filter(requested_by_id=user_id)
    if status:
        query = query.filter(status=status)
    return await _paginate(query, limit, cursor)


async def list_all(status=None, provider=None, user_id=None, cursor=None, limit=50):
    _validate_status(status)
    if provider is not None and provider not in service._PROVIDER_FLAG:
        raise HTTPException(
            status_code=422, detail="Unknown provider: {}".format(provider)
        )
    query = DownloadRequests.all()
    if status:
        query = query.filter(status=status)
    if provider:
        query = query.filter(provider=provider)
    if user_id is not None:
        query = query.filter(requested_by_id=user_id)
    return await _paginate(query, limit, cursor)


async def get_request(request_id):
    return (
        await DownloadRequests.filter(id=request_id)
        .prefetch_related("requested_by")
        .first()
    )


async def cancel_request(request):
    """Cooperatively cancel an active request (the worker aborts between
    stages). Only valid from an active state."""
    if request.status not in service.ACTIVE_STATES:
        raise HTTPException(status_code=409, detail="Request is already finished")
    request.status = "cancelled"
    request.error_kind = "cancelled"
    from datetime import datetime, timezone

    request.finished_at = datetime.now(timezone.utc)
    await request.save(update_fields=["status", "error_kind", "finished_at"])
    return request


async def retry_request(request):
    """Re-queue a failed or cancelled request. Re-checks the enable gate."""
    if request.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail="Only failed or cancelled requests can be retried",
        )
    if not await service.downloads_enabled() or not await service.provider_enabled(
        request.provider
    ):
        raise HTTPException(
            status_code=403,
            detail="The {} provider is disabled".format(request.provider),
        )
    request.status = "queued"
    request.error = None
    request.error_kind = None
    request.progress = 0.0
    request.finished_at = None
    request.started_at = None
    await request.save(
        update_fields=[
            "status",
            "error",
            "error_kind",
            "progress",
            "finished_at",
            "started_at",
        ]
    )
    job = await submit_job(
        "fetch_track",
        payload={"request_id": request.id},
        user_id=request.requested_by_id,
        queue=QUEUE_HEAVY,
    )
    request = await get_request(request.id)
    if request.job_id is None:
        request.job_id = job.id
        await request.save(update_fields=["job_id"])
    return request
