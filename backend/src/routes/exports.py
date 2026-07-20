"""
DJ bundle export routes (MOO-86): poll a running export, download the ZIP.

Submission lives on the crate (POST /crates/{id}/export) because that is what
is being exported; these two are the artifact side. Both are creator-or-owner
only: an export bundle is a pile of audio files, so it never gets an
unauthenticated or signed direct-object URL -- the SameSite=Lax session cookie
already makes a plain <a download> work same-site.
"""
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from src.auth.jwthandler import get_current_user
from src.database.models import Jobs
from src.export import bundle
from src.schemas.jobs import JobOut
from src.schemas.users import UserOutSchema
from src.security import audit
from src.security.authz import ensure_owner_or_403
from src.security.paths import safe_join
from src.utils import storage

router = APIRouter(prefix="/exports", tags=["exports"])


async def _get_export_job(job_id: int, user):
    job = await Jobs.get_or_none(id=job_id, kind="export_crate")
    if job is None:
        raise HTTPException(status_code=404, detail="Export not found")
    ensure_owner_or_403(job.created_by_id, user, detail="This export is not yours")
    return job


@router.get("/{job_id}", response_model=JobOut)
async def get_export(
    job_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> JobOut:
    """
    One export job: progress while it runs, and on success the result envelope
    (download_url, bundle_filename, zip_size_bytes, track_count, skipped,
    expires_at).
    """
    return JobOut.from_orm(await _get_export_job(job_id, current_user))


@router.get("/{job_id}/download")
async def download_export(
    job_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
):
    """
    The bundle ZIP. The artifact path is recomputed from the job id -- no part
    of it is ever taken from the request -- and re-checked against /library
    before it is served.
    """
    job = await _get_export_job(job_id, current_user)
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail="Export is not ready yet")

    result = job.result or {}
    filename = result.get("bundle_filename") or "export.zip"
    path = safe_join(bundle.export_dir(job.id), filename)
    library_root = os.path.realpath(storage.LIBRARY_PATH)
    if not path.startswith(library_root + os.sep) or not os.path.isfile(path):
        raise HTTPException(status_code=410, detail="Export expired")

    await audit.audit_event(
        audit.EXPORT_DOWNLOADED,
        request=request,
        actor=current_user,
        target_type="job",
        target_id=job.id,
        detail={"format": (job.payload or {}).get("format")},
    )
    return FileResponse(
        path,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename*=utf-8''{}".format(
                quote(filename)
            )
        },
    )
