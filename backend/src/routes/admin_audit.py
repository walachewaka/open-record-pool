"""
Admin audit-log view (MOO-89). Read-only; the table is append-only and has no
mutation endpoints. Guarded by the existing view_reports permission.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q

from src.auth.permissions import require_permission
from src.database.models import AuditLog

router = APIRouter(prefix="/admin", tags=["admin: audit"])

_reports = Depends(require_permission("view_reports"))


@router.get("/audit", response_model=Dict[str, Any], dependencies=[_reports])
async def list_audit(
    q: Optional[str] = Query(None, description="Substring over actor / target"),
    event: Optional[str] = Query(None, description="Exact event or family prefix"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    qs = AuditLog.all()
    if event:
        if event.endswith("."):
            qs = qs.filter(event__startswith=event)
        else:
            qs = qs.filter(event=event)
    if q:
        qs = qs.filter(Q(actor_username__icontains=q) | Q(target_id__icontains=q))

    total = await qs.count()
    rows = (
        await qs.order_by("-id").offset((page - 1) * page_size).limit(page_size).all()
    )
    items = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "event": r.event,
            "actor_id": r.actor_id,
            "actor_username": r.actor_username,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "ip": r.ip,
            "detail": r.detail,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
