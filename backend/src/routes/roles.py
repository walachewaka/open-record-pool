"""
Admin roles & permissions matrix routes (MOO-71).
"""
from fastapi import APIRouter, Depends, Request

import src.crud.roles as crud
from src.auth.permissions import require_permission
from src.schemas.admin import RoleMatrixResponse, RoleUpdateSchema
from src.schemas.users import UserOutSchema
from src.security import audit

router = APIRouter(prefix="/admin/roles", tags=["admin: roles"])


@router.get(
    "",
    response_model=RoleMatrixResponse,
    dependencies=[Depends(require_permission("manage_roles"))],
)
async def get_roles_matrix() -> RoleMatrixResponse:
    """
    The full permission matrix: permissions (rows) x roles (columns). Owner is
    reported locked with every permission on.
    """
    return RoleMatrixResponse(**await crud.get_matrix())


@router.put("/{role}", response_model=RoleMatrixResponse)
async def update_role_permissions(
    request: Request,
    role: str,
    payload: RoleUpdateSchema,
    actor: UserOutSchema = Depends(require_permission("manage_roles")),
) -> RoleMatrixResponse:
    """
    Overwrite one non-owner role's permissions. Returns the whole matrix so the
    caller can refresh it in one round trip.
    """
    matrix = await crud.update_role(role, payload.permissions)
    await audit.audit_event(
        audit.ROLE_MATRIX_UPDATED,
        request=request,
        actor=actor,
        target_type="role",
        target_id=role,
        detail={"permissions": payload.permissions},
    )
    return RoleMatrixResponse(**matrix)
