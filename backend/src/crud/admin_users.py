"""
CRUD for administering users from the admin console (MOO-71).

These operations layer on top of the ADMIN_USERNAME bootstrap gating without
weakening it: only a caller with the manage_users permission reaches them (the
route enforces that), and the Owner account is protected here.
"""
from passlib.context import CryptContext
from fastapi import HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.functions import Count

from src.database.models import Users

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Roles assignable through the admin surface. "owner" is deliberately absent:
# the Owner is whoever holds ADMIN_USERNAME and is promoted on boot, never
# assigned here, so the pool always has exactly one Owner.
ASSIGNABLE_ROLES = ["admin", "curator", "member"]
PLANS = ["free", "pro", "crew"]
STATUSES = ["active", "suspended", "pending", "invited"]


def _validate_choice(field, value, allowed):
    if value is not None and value not in allowed:
        raise HTTPException(
            status_code=422,
            detail="{} must be one of: {}".format(field, ", ".join(allowed)),
        )


def _row(user):
    """Map a user (annotated with download_count) to an AdminUserSchema dict."""
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "plan": user.plan,
        "status": user.status,
        "downloads": int(getattr(user, "download_count", 0) or 0),
        "joined": user.created_at,
    }


async def list_users(q=None, role=None, plan=None, status=None, page=1, page_size=50):
    """A filtered, paginated page of users for the admin table."""
    query = Users.all()
    if q:
        text = q.strip()
        query = query.filter(
            Q(username__icontains=text)
            | Q(full_name__icontains=text)
            | Q(email__icontains=text)
        )
    if role:
        query = query.filter(role=role)
    if plan:
        query = query.filter(plan=plan)
    if status:
        query = query.filter(status=status)
    total = await query.count()
    users = (
        await query.annotate(download_count=Count("downloads"))
        .order_by("id")
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [_row(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_user_row(user_id):
    user = (
        await Users.filter(id=user_id)
        .annotate(download_count=Count("downloads"))
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _row(user)


async def create_user(payload):
    """Create/invite a user with an admin-chosen role/plan/status."""
    _validate_choice("role", payload.role, ASSIGNABLE_ROLES)
    _validate_choice("plan", payload.plan, PLANS)
    _validate_choice("status", payload.status, STATUSES)
    password = pwd_context.hash(payload.password) if payload.password else None
    try:
        user = await Users.create(
            username=payload.username,
            full_name=payload.full_name,
            email=payload.email,
            password=password,
            role=payload.role,
            plan=payload.plan,
            status=payload.status,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Sorry, that username already exists."
        )
    return await get_user_row(user.id)


async def update_user(user_id, payload):
    """Change a user's role/plan/status/profile. The Owner is protected."""
    user = await Users.get_or_none(id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    _validate_choice("role", payload.role, ASSIGNABLE_ROLES)
    _validate_choice("plan", payload.plan, PLANS)
    _validate_choice("status", payload.status, STATUSES)

    if user.role == "owner" and (
        (payload.role is not None and payload.role != "owner")
        or (payload.status is not None and payload.status != "active")
    ):
        raise HTTPException(
            status_code=422,
            detail="The Owner account cannot be demoted or suspended.",
        )

    fields = payload.dict(exclude_unset=True)
    if "password" in fields:
        pw = fields.pop("password")
        user.password = pwd_context.hash(pw) if pw else None
    for field, value in fields.items():
        setattr(user, field, value)
    await user.save()
    return await get_user_row(user.id)


async def delete_user(user_id):
    """Delete a user. The Owner cannot be deleted."""
    user = await Users.get_or_none(id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "owner":
        raise HTTPException(
            status_code=422, detail="The Owner account cannot be deleted."
        )
    await user.delete()
    return {"message": "Deleted user {}".format(user_id)}
