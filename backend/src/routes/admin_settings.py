"""
Admin instance-settings routes (MOO-71): the settings store, the "Scan now"
trigger for the /music extraction, and the search reindex + status surface
(MOO-79).
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

import src.crud.settings as crud
from src.auth.permissions import require_permission
from src.jobs.queue import submit_job, workers_enabled
from src.jobs.tasks import scan_pending
from src.schemas.admin import SettingsUpdateSchema
from src.schemas.jobs import JobOut
from src.schemas.users import UserOutSchema
from src.search.es import INDEX_ALIAS, es_enabled, es_ping
from src.security import audit
from src.security.ratelimit import rate_limit

router = APIRouter(prefix="/admin/settings", tags=["admin: settings"])

_settings = Depends(require_permission("site_settings"))


@router.get("", response_model=Dict[str, Any], dependencies=[_settings])
async def get_settings() -> Dict[str, Any]:
    """The full grouped instance settings (defaults overlaid with overrides)."""
    return await crud.get_all()


@router.put("", response_model=Dict[str, Any])
async def update_settings(
    request: Request,
    payload: SettingsUpdateSchema,
    actor: UserOutSchema = Depends(require_permission("site_settings")),
) -> Dict[str, Any]:
    """Apply a partial grouped settings update and return the full settings."""
    result = await crud.update(payload.__root__)
    await audit.audit_event(
        audit.SETTINGS_UPDATED,
        request=request,
        actor=actor,
        target_type="settings",
        detail={"groups": list((payload.__root__ or {}).keys())},
    )
    return result


@router.post("/scan", response_model=JobOut, status_code=202)
async def scan_now(
    current_user: UserOutSchema = Depends(require_permission("site_settings")),
) -> JobOut:
    """
    "Scan now": enqueue the /music extraction/sync as a background job
    (MOO-77) and return the job envelope. The task records the last-scan
    summary for the dashboard health panel when it finishes. In inline mode
    the returned job is already terminal with the result set.
    """
    if await scan_pending():
        raise HTTPException(
            status_code=409, detail="A library scan is already queued or running"
        )
    return await submit_job("scan_library", user_id=current_user.id)


@router.post("/reindex", response_model=JobOut, status_code=202)
async def reindex(
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("site_settings")),
) -> JobOut:
    """
    Zero-downtime full search reindex (MOO-79): stream every song from
    PostgreSQL into the next versioned index and atomically swap the
    orp-tracks alias. Returns the MOO-77 job envelope; poll
    GET /admin/jobs/{id}. In inline mode the envelope comes back terminal.
    """
    await rate_limit("admin-reindex", str(current_user.id), limit=3, window_seconds=60)
    if not es_enabled():
        raise HTTPException(
            status_code=503,
            detail="Search engine unavailable; reindex cannot run",
        )
    if not workers_enabled() and not await es_ping():
        raise HTTPException(
            status_code=503,
            detail="Search engine unavailable; reindex cannot run",
        )
    await audit.audit_event(
        "search.reindex.requested",
        request=request,
        actor=current_user,
        target_type="search_index",
        target_id=INDEX_ALIAS,
    )
    return await submit_job("search_reindex", user_id=current_user.id)
