"""
CRUD (create-read-update-delete) operations for users.
"""
import os

from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist, IntegrityError

from src.auth.users import pwd_context
from src.database.models import Users
from src.schemas.token import Status
from src.schemas.users import UserOutSchema


def get_admin_username() -> str:
    """The username of the single admin account, configured via ADMIN_USERNAME."""
    return os.environ.get("ADMIN_USERNAME", "").strip()


async def promote_admin_to_owner() -> None:
    """
    Ensure the configured admin account holds the Owner role (MOO-71).

    The role system layers on top of the ADMIN_USERNAME bootstrap: whichever
    account owns that username is the pool Owner. This is idempotent and safe
    to run on every start, so an admin created before the role column existed
    (defaulted to Member by the migration) is promoted on the next boot. The
    Owner can never be left suspended, so we also reactivate it.
    """
    admin_username = get_admin_username()
    if not admin_username:
        return
    admin = await Users.get_or_none(username=admin_username)
    if admin is None:
        return
    changed = False
    if admin.role != "owner":
        admin.role = "owner"
        changed = True
    if admin.status == "suspended":
        admin.status = "active"
        changed = True
    if changed:
        await admin.save(update_fields=["role", "status", "modified_at"])


async def ensure_can_create_user(current_user, new_username: str) -> None:
    """
    Enforce that only the admin may create users (#41, #16).

    Admin gating is only active when ADMIN_USERNAME is configured (see the
    Docker Compose configuration). When it is unset, registration stays open
    so existing deployments keep working.

    The admin account bootstraps itself: while no users exist yet, the only
    account that may be created is the configured admin. Afterwards, a new
    user can only be created by the admin.
    """
    admin_username = get_admin_username()
    if not admin_username:
        return

    if current_user is not None and current_user.username == admin_username:
        return

    if await Users.all().count() == 0 and new_username == admin_username:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the admin can create users.",
    )


async def create_user(user) -> UserOutSchema:
    """
    Creates a user.
    """
    user.password = pwd_context.hash(user.password)

    try:
        user_obj = await Users.create(**user.dict(exclude_unset=True))
    except IntegrityError:
        # A duplicate username is a conflict on an existing resource, not an
        # authentication failure. Returning 401 here made the frontend treat it
        # as an auth error instead of showing the message to the user (#35, #43).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sorry, that username already exists.",
        )

    # Bootstrapping the admin account (the first /register on an empty pool)
    # makes it the Owner right away, not only after the next restart (MOO-71).
    if user_obj.username == get_admin_username():
        await promote_admin_to_owner()
        user_obj = await Users.get(id=user_obj.id)

    return await UserOutSchema.from_tortoise_orm(user_obj)


async def delete_user(user_id, current_user) -> Status:
    """
    Deletes a user.
    """
    try:
        db_user = await UserOutSchema.from_queryset_single(Users.get(id=user_id))
    except DoesNotExist:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    if db_user.id == current_user.id:
        deleted_count = await Users.filter(id=user_id).delete()
        if not deleted_count:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        return Status(message=f"Deleted user {user_id}")

    raise HTTPException(status_code=403, detail="Not authorized to delete")
