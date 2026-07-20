"""
Admin job routes (MOO-77): keyset-paginated job list and job detail. The
detail route lets a job's creator poll their own job without view_reports
(the Browse rescan button posts /songs/extract and polls the returned id).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth.jwthandler import get_current_user
from src.auth.permissions import has_permission, require_permission
from src.database.models import Jobs
from src.schemas.jobs import JobListResponse, JobOut
from src.schemas.users import UserOutSchema
from src.utils.pagination import decode_cursor, encode_cursor, keyset_filter

router = APIRouter(prefix="/admin/jobs", tags=["admin: jobs"])

JOB_STATUSES = ["queued", "running", "succeeded", "failed", "cancelled"]


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by job status"),
    kind: Optional[str] = Query(None, description="Filter by job kind"),
    cursor: Optional[str] = Query(None, description="Keyset cursor (id DESC)"),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(require_permission("view_reports")),
) -> JobListResponse:
    """
    The background jobs, newest first, keyset-paginated (never OFFSET —
    MOO-77 scale rules).
    """
    if status is not None and status not in JOB_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of: {}".format(", ".join(JOB_STATUSES)),
        )
    query = Jobs.all()
    if status:
        query = query.filter(status=status)
    if kind:
        query = query.filter(kind=kind)
    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != "id" or token["o"] != "desc":
            raise HTTPException(status_code=422, detail="Invalid cursor")
        try:
            last_id = int(token["k"][-1])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid cursor")
        query = query.filter(keyset_filter("id", "desc", last_id, last_id))
    jobs = await query.order_by("-id").limit(limit)
    items = [JobOut.from_orm(job) for job in jobs]
    next_cursor = None
    if len(items) == limit:
        next_cursor = encode_cursor("id", "desc", [items[-1].id, items[-1].id])
    return JobListResponse(items=items, next_cursor=next_cursor)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> JobOut:
    """
    One job. Object-level authorization: the caller needs view_reports OR to
    be the job's creator (so members who triggered a scan can poll it).
    """
    job = await Jobs.get_or_none(id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.created_by_id != current_user.id and not await has_permission(
        current_user, "view_reports"
    ):
        raise HTTPException(
            status_code=403, detail="You do not have permission: view_reports"
        )
    return JobOut.from_orm(job)
