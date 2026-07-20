"""
The short-lived OIDC transaction cookie (MOO-88).

Between /auth/oidc/{provider}/start and the callback we must remember the
`state`, the `nonce`, and the PKCE `code_verifier`. They live in a signed,
httponly cookie (HS256 over the app's SECRET_KEY) rather than in the database:
it expires by itself, needs no table and no garbage collection, and works
across uvicorn workers. SameSite=Lax is what makes the cookie arrive on the
IDP's top-level redirect back to us -- the same property the auth cookie relies
on. The user's own browser being able to read its own code_verifier is not a
threat; the user is the legitimate party.
"""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta

import jwt

from src.auth.jwthandler import ALGORITHM, SECRET_KEY
from src.config import resolve_cookie_secure

COOKIE_NAME = "oidc_txn"
COOKIE_PATH = "/auth/oidc"
TXN_TTL_SECONDS = 600
_PURPOSE = "oidc_txn"


def pkce_pair():
    """A PKCE (verifier, S256 challenge) pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def mint_txn(provider_id, mode="login", link_user_id=None):
    """
    Mint a transaction. Returns (cookie_value, state, nonce, code_challenge);
    the verifier stays inside the cookie.
    """
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    claims = {
        "purpose": _PURPOSE,
        "provider": provider_id,
        "state": state,
        "nonce": nonce,
        "code_verifier": verifier,
        "mode": mode,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(seconds=TXN_TTL_SECONDS),
    }
    if link_user_id is not None:
        claims["link_user_id"] = link_user_id
    token = jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)
    if isinstance(token, bytes):  # PyJWT 1.x compatibility
        token = token.decode("utf-8")
    return token, state, nonce, challenge


def read_txn(request, provider_id):
    """
    The transaction for this callback, or None when the cookie is missing,
    forged, expired, or belongs to a different provider.
    """
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        claims = jwt.decode(raw, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if claims.get("purpose") != _PURPOSE:
        return None
    if claims.get("provider") != provider_id:
        return None
    return claims


def set_txn_cookie(response, value):
    response.set_cookie(
        COOKIE_NAME,
        value=value,
        httponly=True,
        max_age=TXN_TTL_SECONDS,
        expires=TXN_TTL_SECONDS,
        samesite="Lax",
        secure=resolve_cookie_secure(),
        path=COOKIE_PATH,
    )


def clear_txn_cookie(response):
    """A transaction is single-use: every callback drops the cookie."""
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
