"""
CRUD for the role permission matrix (MOO-71).
"""
from fastapi import HTTPException

from src.auth.permissions import (
    OWNER,
    PERMISSIONS,
    PERMISSION_KEYS,
    ROLE_DEFS,
    default_permissions,
    effective_permissions,
)
from src.database.models import RolePermissions


async def get_matrix():
    """
    The whole permission matrix: every role with its effective permissions.
    Owner is reported locked (all-on, not editable).
    """
    roles = []
    for role_def in ROLE_DEFS:
        role = role_def["key"]
        roles.append(
            {
                "key": role,
                "name": role_def["name"],
                "description": role_def["description"],
                "locked": role == OWNER,
                "permissions": await effective_permissions(role),
            }
        )
    return {
        "permissions": [{"key": key, "label": label} for key, label in PERMISSIONS],
        "roles": roles,
    }


async def update_role(role, permissions):
    """
    Overwrite the stored permissions for a non-owner role and return the whole
    matrix. Owner is locked; unknown roles or permission keys are rejected.
    """
    if role == OWNER:
        raise HTTPException(
            status_code=403, detail="The Owner role's permissions are locked on."
        )
    if not any(rd["key"] == role for rd in ROLE_DEFS):
        raise HTTPException(status_code=404, detail="Unknown role: {}".format(role))
    unknown = [key for key in permissions if key not in PERMISSION_KEYS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail="Unknown permission(s): {}".format(", ".join(sorted(unknown))),
        )
    # Start from the role's defaults so an omitted key keeps a sensible value,
    # then apply the caller's booleans.
    resolved = default_permissions(role)
    for key, value in permissions.items():
        resolved[key] = bool(value)
    await RolePermissions.update_or_create(
        role=role, defaults={"permissions": resolved}
    )
    return await get_matrix()
