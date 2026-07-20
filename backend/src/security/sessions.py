"""
Server-side session records backing the cookie-JWT (MOO-89).

The JWT stays the transport (SameSite=Lax httponly cookie), but every login
also writes an `auth_sessions` row keyed by the token's `jti`. Authentication
now checks that row, which makes sessions revocable: logout, "log out
everywhere", and an admin killing a user's sessions all take effect
immediately, and an absolute timeout can outlive the short access token.

Timeouts:
- idle timeout  = the JWT's own expiry (ACCESS_TOKEN_EXPIRE_MINUTES, default 30)
- absolute cap  = SESSION_ABSOLUTE_HOURS (default 12), stored on the row
- rotation      = while active and past half the token lifetime, a fresh token
  (same jti, new exp) is issued via Set-Cookie so active users are not logged
  out at 30 minutes but idle ones are.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from src.config import resolve_cookie_secure
from src.database.models import AuthSessions

COOKIE_NAME = "Authorization"


def _utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Coerce a datetime to timezone-aware UTC. The ORM returns aware datetimes on
    Postgres (TIMESTAMPTZ) but the value we stored may be naive (or vice versa
    on sqlite), so every comparison goes through this.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def access_token_expire_minutes() -> int:
    try:
        return int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    except ValueError:
        return 30


def session_absolute_hours() -> int:
    try:
        return int(os.environ.get("SESSION_ABSOLUTE_HOURS", "12"))
    except ValueError:
        return 12


async def create_session(user, request=None) -> str:
    """Create a session row for `user` and return its jti (uuid4 hex)."""
    jti = uuid4().hex
    ip = None
    user_agent = None
    if request is not None:
        client = getattr(request, "client", None)
        if client is not None and getattr(client, "host", None):
            ip = client.host
        user_agent = request.headers.get("user-agent")
        if user_agent:
            user_agent = user_agent[:255]
    await AuthSessions.create(
        jti=jti,
        user_id=user.id,
        expires_at=_utcnow() + timedelta(hours=session_absolute_hours()),
        ip=ip,
        user_agent=user_agent,
    )
    return jti


async def validate_session(jti: Optional[str]):
    """
    Return the live AuthSessions row for `jti`, or None when the session is
    unknown, revoked, or past its absolute expiry. Refreshes last_seen_at at
    most once a minute so a busy session does not write on every request.
    """
    if not jti:
        return None
    row = await AuthSessions.get_or_none(jti=jti)
    if row is None or row.revoked_at is not None:
        return None
    now = _utcnow()
    expires_at = _aware(row.expires_at)
    if expires_at is not None and now > expires_at:
        return None
    last_seen = _aware(row.last_seen_at)
    if last_seen is None or (now - last_seen).total_seconds() > 60:
        row.last_seen_at = now
        await row.save(update_fields=["last_seen_at"])
    return row


async def revoke_session(jti: Optional[str]) -> int:
    if not jti:
        return 0
    return await AuthSessions.filter(jti=jti, revoked_at__isnull=True).update(
        revoked_at=_utcnow()
    )


async def revoke_all(user_id: int) -> int:
    return await AuthSessions.filter(user_id=user_id, revoked_at__isnull=True).update(
        revoked_at=_utcnow()
    )


def set_auth_cookie(response, token: str) -> None:
    """Attach the auth cookie with the current security flags."""
    max_age = access_token_expire_minutes() * 60
    response.set_cookie(
        COOKIE_NAME,
        value="Bearer {}".format(token),
        httponly=True,
        max_age=max_age,
        expires=max_age,
        samesite="Lax",
        secure=resolve_cookie_secure(),
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME)
    # Belt and braces: an explicit expired cookie, matching flags.
    response.set_cookie(
        COOKIE_NAME,
        value="",
        httponly=True,
        max_age=0,
        expires=0,
        samesite="Lax",
        secure=resolve_cookie_secure(),
    )


class SessionCookieMiddleware:
    """
    Deliver a rotated token (MOO-89). get_current_user stashes the new JWT on
    request.state.reissue_token (which lives in scope["state"]); here we append
    the matching Set-Cookie to the response start headers. Pure ASGI so it never
    buffers a streaming response.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                state = scope.get("state") or {}
                token = state.get("reissue_token")
                if token:
                    from starlette.datastructures import MutableHeaders
                    from starlette.responses import Response

                    tmp = Response()
                    set_auth_cookie(tmp, token)
                    headers = MutableHeaders(scope=message)
                    for key, value in tmp.raw_headers:
                        if key == b"set-cookie":
                            headers.append("set-cookie", value.decode("latin-1"))
            await send(message)

        await self.app(scope, receive, send_wrapper)
