"""
Admin user-management routes (MOO-71). All require the manage_users permission.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import src.crud.admin_users as crud
from src.auth.permissions import require_permission
from src.database.models import AuthSessions, Users
from src.schemas.admin import (
    AdminUserCreateSchema,
    AdminUserListResponse,
    AdminUserSchema,
    AdminUserUpdateSchema,
)
from src.schemas.token import Status
from src.schemas.users import UserOutSchema
from src.security import audit, sessions

router = APIRouter(prefix="/admin/users", tags=["admin: users"])

_manage_users = Depends(require_permission("manage_users"))


@router.get("", response_model=AdminUserListResponse, dependencies=[_manage_users])
async def list_users(
    q: Optional[str] = Query(None, description="Search name/username/email"),
    role: Optional[str] = Query(None),
    plan: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=300),
) -> AdminUserListResponse:
    """The users table with search and role/plan/status filters."""
    return AdminUserListResponse(
        **await crud.list_users(
            q=q, role=role, plan=plan, status=status, page=page, page_size=page_size
        )
    )


@router.post("", response_model=AdminUserSchema)
async def create_user(
    request: Request,
    payload: AdminUserCreateSchema,
    actor: UserOutSchema = Depends(require_permission("manage_users")),
) -> AdminUserSchema:
    """Invite/create a user with an admin-chosen role, plan, and status."""
    created = await crud.create_user(payload)
    await audit.audit_event(
        audit.USER_CREATED,
        request=request,
        actor=actor,
        target_type="user",
        target_id=created.get("id"),
        detail={"username": created.get("username"), "role": created.get("role")},
    )
    return AdminUserSchema(**created)


@router.get("/{user_id}", response_model=AdminUserSchema, dependencies=[_manage_users])
async def get_user(user_id: int) -> AdminUserSchema:
    """One user's admin detail (the drawer)."""
    return AdminUserSchema(**await crud.get_user_row(user_id))


@router.patch("/{user_id}", response_model=AdminUserSchema)
async def update_user(
    request: Request,
    user_id: int,
    payload: AdminUserUpdateSchema,
    actor: UserOutSchema = Depends(require_permission("manage_users")),
) -> AdminUserSchema:
    """Change a user's role/plan/status or profile (suspend/reinstate here too)."""
    updated = await crud.update_user(user_id, payload)
    await audit.audit_event(
        audit.USER_UPDATED,
        request=request,
        actor=actor,
        target_type="user",
        target_id=user_id,
        detail=payload.dict(exclude_unset=True),
    )
    # Note: suspension is enforced on every request by get_current_user (403),
    # so a suspended user is locked out immediately without revoking the row.
    # To also invalidate their cookies, use DELETE /admin/users/{id}/sessions.
    return AdminUserSchema(**updated)


@router.delete("/{user_id}", response_model=Status)
async def delete_user(
    request: Request,
    user_id: int,
    actor: UserOutSchema = Depends(require_permission("manage_users")),
) -> Status:
    """Delete a user (the Owner cannot be deleted)."""
    result = await crud.delete_user(user_id)
    await audit.audit_event(
        audit.USER_DELETED,
        request=request,
        actor=actor,
        target_type="user",
        target_id=user_id,
    )
    return Status(**result)


def _admin_session_item(row) -> Dict[str, Any]:
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "ip": row.ip,
        "user_agent": row.user_agent,
    }


@router.get("/{user_id}/sessions", dependencies=[_manage_users])
async def list_user_sessions(user_id: int) -> List[Dict[str, Any]]:
    """A user's active sessions (admin view)."""
    if await Users.get_or_none(id=user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.now(timezone.utc)
    rows = (
        await AuthSessions.filter(
            user_id=user_id, revoked_at__isnull=True, expires_at__gt=now
        )
        .order_by("-created_at")
        .all()
    )
    return [_admin_session_item(r) for r in rows]


@router.delete("/{user_id}/sessions")
async def revoke_user_sessions(
    request: Request,
    user_id: int,
    actor: UserOutSchema = Depends(require_permission("manage_users")),
) -> Dict[str, int]:
    """Revoke all of a user's sessions (admin kill)."""
    if await Users.get_or_none(id=user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    revoked = await sessions.revoke_all(user_id)
    await audit.audit_event(
        audit.SESSION_REVOKED_ADMIN,
        request=request,
        actor=actor,
        target_type="user",
        target_id=user_id,
        detail={"revoked": revoked},
    )
    return {"revoked": revoked}
