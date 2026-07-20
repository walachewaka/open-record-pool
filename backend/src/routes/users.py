"""
Our users routes.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from tortoise.contrib.fastapi import HTTPNotFoundError

import src.crud.users as crud
from src.auth import oidc
from src.auth.permissions import effective_permissions
from src.auth.users import validate_user
from src.schemas.token import Status
from src.schemas.users import UserInSchema, UserOutSchema, WhoAmISchema
from src.security import audit
from src.security import ratelimit
from src.security import sessions

from src.auth.jwthandler import (
    create_access_token,
    get_current_user,
    get_current_user_optional,
)


router = APIRouter()


@router.post("/register", response_model=UserOutSchema)
async def create_user(
    request: Request,
    user: UserInSchema,
    current_user=Depends(get_current_user_optional),
) -> UserOutSchema:
    # Anonymous registration attempts are abuse-prone; the admin-authenticated
    # create path (invites) is not limited (MOO-89).
    if current_user is None:
        await ratelimit.rate_limit("register_ip", ratelimit.client_ip(request), 5, 3600)
    await crud.ensure_can_create_user(current_user, user.username)
    created = await crud.create_user(user)
    await audit.audit_event(
        audit.USER_CREATED,
        request=request,
        actor=current_user,
        target_type="user",
        target_id=created.id,
        detail={"username": created.username},
    )
    return created


@router.post("/login")
async def login(request: Request, user: OAuth2PasswordRequestForm = Depends()):
    # An IDP-only pool (LOCAL_LOGIN_ENABLED=false, MOO-88) refuses the local
    # form outright; the gate hides it too, via GET /auth/methods.
    if not oidc.local_login_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local sign-in is disabled on this pool.",
        )

    ip = ratelimit.client_ip(request)
    try:
        # Per-IP and per-username fixed windows. A successful login clears both,
        # so only repeated failures accumulate toward the limit (MOO-89).
        await ratelimit.rate_limit("login_ip", ip, 5, 60)
        await ratelimit.rate_limit("login_user", user.username, 10, 300)
    except HTTPException as exc:
        if exc.status_code == 429:
            await audit.audit_event(
                audit.RATE_LIMITED,
                request=request,
                detail={"username": user.username, "endpoint": "login"},
            )
        raise

    try:
        db_user = await validate_user(user)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            await audit.audit_event(
                audit.LOGIN_FAILURE,
                request=request,
                detail={"username": user.username},
            )
        raise

    # Suspended accounts cannot log in (MOO-71). Reached only after a correct
    # password, so it is not an anonymous enumeration vector (SECURITY.md).
    if db_user.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended.",
        )

    # A JIT-provisioned account awaiting admin approval (MOO-88 `invite` policy)
    # cannot log in locally either. Same reasoning as suspension: only reachable
    # after a correct password, so it is not an enumeration vector.
    if db_user.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is awaiting approval.",
        )

    jti = await sessions.create_session(db_user, request)
    access_token = create_access_token(
        data={"sub": db_user.username, "jti": jti},
        expires_delta=timedelta(minutes=sessions.access_token_expire_minutes()),
    )
    token = jsonable_encoder(access_token)

    # Clear the failure buckets now that the credentials checked out.
    await ratelimit.rate_limit_clear("login_ip", ip)
    await ratelimit.rate_limit_clear("login_user", user.username)
    await audit.audit_event(
        audit.LOGIN_SUCCESS,
        request=request,
        actor=db_user,
        detail={"username": db_user.username},
    )

    content = {"message": "You've successfully logged in. Welcome back!"}
    response = JSONResponse(content=content)
    sessions.set_auth_cookie(response, token)
    return response


@router.post("/logout")
async def logout(request: Request, current_user=Depends(get_current_user_optional)):
    """
    Revoke the current session and clear the cookie. Uses the optional
    dependency so an already-expired session can still clear its cookie without
    tripping the frontend 401 interceptor.
    """
    jti = getattr(request.state, "session_jti", None)
    if jti:
        await sessions.revoke_session(jti)
    response = JSONResponse(content={"message": "Logged out."})
    sessions.clear_auth_cookie(response)
    await audit.audit_event(audit.LOGOUT, request=request, actor=current_user)
    return response


@router.post("/logout-all")
async def logout_all(
    request: Request, current_user: UserOutSchema = Depends(get_current_user)
):
    """Revoke every one of the current user's sessions and clear the cookie."""
    revoked = await sessions.revoke_all(current_user.id)
    response = JSONResponse(content={"revoked": revoked})
    sessions.clear_auth_cookie(response)
    await audit.audit_event(audit.LOGOUT_ALL, request=request, actor=current_user)
    return response


def _session_item(row, current_jti=None) -> dict:
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "ip": row.ip,
        "user_agent": row.user_agent,
        "current": current_jti is not None and row.jti == current_jti,
    }


@router.get("/users/me/sessions")
async def list_my_sessions(
    request: Request, current_user: UserOutSchema = Depends(get_current_user)
):
    """My active sessions (unrevoked, unexpired), newest first."""
    from datetime import datetime, timezone

    from src.database.models import AuthSessions

    current_jti = getattr(request.state, "session_jti", None)
    now = datetime.now(timezone.utc)
    rows = (
        await AuthSessions.filter(
            user_id=current_user.id, revoked_at__isnull=True, expires_at__gt=now
        )
        .order_by("-created_at")
        .all()
    )
    return [_session_item(r, current_jti) for r in rows]


@router.delete("/users/me/sessions/{session_id}")
async def revoke_my_session(
    session_id: int, current_user: UserOutSchema = Depends(get_current_user)
):
    """Revoke one of MY sessions. Someone else's or unknown id -> 404 (IDOR)."""
    from datetime import datetime, timezone

    from src.database.models import AuthSessions

    updated = await AuthSessions.filter(
        id=session_id, user_id=current_user.id, revoked_at__isnull=True
    ).update(revoked_at=datetime.now(timezone.utc))
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session revoked"}


@router.get(
    "/users/whoami",
    response_model=WhoAmISchema,
    dependencies=[Depends(get_current_user)],
)
async def read_users_me(current_user: UserOutSchema = Depends(get_current_user)):
    from src.database.models import Users

    permissions = await effective_permissions(current_user.role)
    # has_password tells the Account view whether this is an SSO-only account,
    # so it can show "SSO only" and refuse to strand the last sign-in method
    # (MOO-88).
    row = await Users.get_or_none(id=current_user.id)
    return WhoAmISchema(
        **current_user.dict(),
        permissions=permissions,
        has_password=bool(row and row.password),
    )


@router.delete(
    "/user/{user_id}",
    response_model=Status,
    responses={404: {"model": HTTPNotFoundError}},
    dependencies=[Depends(get_current_user)],
)
async def delete_user(
    user_id: int, current_user: UserOutSchema = Depends(get_current_user)
) -> Status:
    return await crud.delete_user(user_id, current_user)
