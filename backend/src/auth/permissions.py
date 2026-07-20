"""
Role/permission model and authorization dependencies for the admin console
(MOO-71).

Every user has a role. The Owner role has every permission, locked on, and is
resolved entirely in code (never stored). The other roles start from the coded
defaults below and can be overridden through the persisted permission matrix
(RolePermissions). require_permission(...) turns a permission into a FastAPI
dependency that 403s when the caller's role lacks it.
"""
from fastapi import Depends, HTTPException

from src.auth.jwthandler import get_current_user
from src.database.models import RolePermissions
from src.schemas.users import UserOutSchema


# Permission keys in matrix (row) order, with their human labels. The keys are
# the stable contract the frontend and the endpoints use.
PERMISSIONS = [
    ("browse_download", "Browse & download"),
    ("create_crates", "Create crates"),
    ("upload_tracks", "Upload tracks"),
    ("edit_metadata", "Edit metadata"),
    ("approve_submissions", "Approve submissions"),
    ("manage_users", "Manage users"),
    ("manage_roles", "Manage roles"),
    ("site_settings", "Site settings"),
    ("view_reports", "View reports"),
    ("manage_billing", "Manage billing"),
]
PERMISSION_KEYS = [key for key, _ in PERMISSIONS]

OWNER = "owner"
ROLES = ["owner", "admin", "curator", "member"]

# Role display metadata (column headers of the matrix).
ROLE_DEFS = [
    {
        "key": "owner",
        "name": "Owner",
        "description": "Full control; cannot be limited.",
    },
    {"key": "admin", "name": "Admin", "description": "Runs the pool day to day."},
    {
        "key": "curator",
        "name": "Curator",
        "description": "Curates and moderates content.",
    },
    {"key": "member", "name": "Member", "description": "Browses and downloads."},
]

# Coded default matrix for the non-owner roles. Owner is always all-on.
_ALL_ON = {key: True for key in PERMISSION_KEYS}
DEFAULT_MATRIX = {
    "owner": dict(_ALL_ON),
    "admin": {
        **_ALL_ON,
        "manage_roles": False,
        "manage_billing": False,
    },
    "curator": {
        "browse_download": True,
        "create_crates": True,
        "upload_tracks": True,
        "edit_metadata": True,
        "approve_submissions": True,
        "manage_users": False,
        "manage_roles": False,
        "site_settings": False,
        "view_reports": False,
        "manage_billing": False,
    },
    "member": {
        "browse_download": True,
        "create_crates": True,
        "upload_tracks": False,
        "edit_metadata": False,
        "approve_submissions": False,
        "manage_users": False,
        "manage_roles": False,
        "site_settings": False,
        "view_reports": False,
        "manage_billing": False,
    },
}


def _normalize(perms):
    """Coerce a permission map to exactly the known keys as booleans."""
    return {key: bool(perms.get(key, False)) for key in PERMISSION_KEYS}


def default_permissions(role):
    """The coded default permissions for a role (unknown roles -> member)."""
    return _normalize(DEFAULT_MATRIX.get(role, DEFAULT_MATRIX["member"]))


async def effective_permissions(role):
    """
    The effective permissions for a role: Owner is all-on and locked; other
    roles are their coded defaults overlaid with any stored overrides.
    """
    if role == OWNER:
        return dict(_ALL_ON)
    base = default_permissions(role)
    row = await RolePermissions.get_or_none(role=role)
    if row and row.permissions:
        for key, value in row.permissions.items():
            if key in base:
                base[key] = bool(value)
    return base


async def has_permission(user, permission):
    """Whether [user]'s role grants [permission]."""
    perms = await effective_permissions(user.role)
    return bool(perms.get(permission))


async def can_view_unpublished(user):
    """
    Whether a user may see non-published tracks (moderators/curators/admins).
    Used to let the admin surface preview draft/pending/rejected tracks that
    are hidden from the member listings.
    """
    perms = await effective_permissions(user.role)
    return bool(perms.get("edit_metadata") or perms.get("approve_submissions"))


def require_permission(permission):
    """
    A FastAPI dependency that allows the request only when the current user's
    role grants [permission], and returns that user.
    """

    async def dependency(
        current_user: UserOutSchema = Depends(get_current_user),
    ) -> UserOutSchema:
        if not await has_permission(current_user, permission):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission: {}".format(permission),
            )
        return current_user

    # Tag the closure so the startup route guard (MOO-89) recognises this route
    # as authorization-declared.
    dependency.__orp_authz__ = permission
    return dependency
