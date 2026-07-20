"""
Handler for our JWT tokens.

JWT tokens carry the session on the client (a SameSite=Lax httponly cookie).
Since MOO-89 every token also carries a `jti` bound to a server-side
`auth_sessions` row, so sessions are revocable and rotate while active.
"""
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from fastapi.security import OAuth2
from fastapi.security.utils import get_authorization_scheme_param
from tortoise.exceptions import DoesNotExist

from src.database.models import Users
from src.schemas.token import TokenData
from src.schemas.users import UserOutSchema
from src.security import sessions


# Retrieve the SECRET_KEY for an environment variable:
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"


def _expire_minutes() -> int:
    return sessions.access_token_expire_minutes()


# Backwards-compatible module constant (still imported by routes.users).
ACCESS_TOKEN_EXPIRE_MINUTES = _expire_minutes()


class OAuth2PasswordBearerCookie(OAuth2):
    """
    OAuth2 password bearer that uses cookies.
    """

    def __init__(
        self,
        token_url: str,
        scheme_name: str = None,
        scopes: dict = None,
        auto_error: bool = True,
    ):
        if not scopes:
            scopes = {}
        flows = OAuthFlowsModel(password={"tokenUrl": token_url, "scopes": scopes})
        super().__init__(flows=flows, scheme_name=scheme_name, auto_error=auto_error)

    async def __call__(self, request: Request) -> Optional[str]:
        authorization: str = request.cookies.get("Authorization")
        scheme, param = get_authorization_scheme_param(authorization)

        if not authorization or scheme.lower() != "bearer":
            if self.auto_error:
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None

        return param


security = OAuth2PasswordBearerCookie(token_url="/login")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Creates the access token. Adds `iat` (used for rotation) and, unless the
    caller already supplied one, a `jti`.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=_expire_minutes())

    to_encode.setdefault("jti", uuid4().hex)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    # PyJWT >= 2 returns str; keep behaviour uniform.
    if isinstance(encoded_jwt, bytes):
        encoded_jwt = encoded_jwt.decode("utf-8")
    return encoded_jwt


def _maybe_rotate(request, payload):
    """
    If the token is past half its lifetime, stash a fresh token (same jti/sub,
    new exp) on request.state so SessionCookieMiddleware re-sets the cookie.
    """
    if request is None:
        return
    try:
        iat = payload.get("iat")
        exp = payload.get("exp")
        if not iat or not exp:
            return
        now = time.time()
        if now >= iat + (exp - iat) / 2.0:
            new_token = create_access_token(
                {"sub": payload.get("sub"), "jti": payload.get("jti")},
                expires_delta=timedelta(minutes=_expire_minutes()),
            )
            request.state.reissue_token = new_token
    except Exception:
        return


get_current_user_authz = "user"


async def get_current_user(request: Request, token: str = Depends(security)):
    """
    Returns the current user, enforcing that the token's session is still live
    (not revoked / not past its absolute expiry) and rotating it while active.
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except jwt.PyJWTError:
        raise credentials_exception

    session = await sessions.validate_session(payload.get("jti"))
    if session is None:
        raise credentials_exception

    try:
        user = await UserOutSchema.from_queryset_single(
            Users.get(username=token_data.username)
        )
    except DoesNotExist:
        raise credentials_exception

    # A suspended account may not use the API even with a still-valid cookie
    # (MOO-71). This guards every authenticated endpoint at once.
    if user.status == "suspended":
        raise HTTPException(
            status_code=403,
            detail="Your account has been suspended.",
        )

    request.state.session_jti = payload.get("jti")
    _maybe_rotate(request, payload)
    return user


get_current_user.__orp_authz__ = "user"


security_optional = OAuth2PasswordBearerCookie(token_url="/login", auto_error=False)


async def get_current_user_optional(
    request: Request, token: Optional[str] = Depends(security_optional)
):
    """
    Returns the current user if a valid, live session cookie is present, else
    None. Never raises. Used by endpoints that behave differently for anonymous
    and authenticated callers (e.g. admin-gated registration, #41).
    """
    if token is None:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            return None
    except jwt.PyJWTError:
        return None

    if await sessions.validate_session(payload.get("jti")) is None:
        return None

    try:
        user = await UserOutSchema.from_queryset_single(Users.get(username=username))
    except DoesNotExist:
        return None

    if user.status == "suspended":
        return None

    request.state.session_jti = payload.get("jti")
    _maybe_rotate(request, payload)
    return user


get_current_user_optional.__orp_authz__ = "optional"
