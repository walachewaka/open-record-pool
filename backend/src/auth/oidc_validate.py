"""
ID-token verification (MOO-88).

The ID token is the only thing we trust from the provider, so it is verified in
full before a single claim is read: RS256 only (an `alg` of `none`/HS256 is
rejected before the key is even looked up -- algorithm confusion is the classic
break here), signature against the provider's own JWKS, issuer/audience/expiry,
and the nonce we minted at /start.

The UserInfo endpoint is never called: Entra v2.0, Google and Okta all deliver
sub/email/email_verified/name (plus `hd`, `tid` and group claims) in the ID
token with the `openid email profile` scopes, so we spare ourselves another
outbound fetch.
"""
import hmac
import json
import time

import jwt
from jwt.algorithms import RSAAlgorithm

from src.auth.oidc_http import OIDCError, fetch_jwks

ALLOWED_ALGORITHMS = ["RS256"]
JWKS_TTL_SECONDS = 3600
LEEWAY_SECONDS = 60

# {jwks_uri: (fetched_at, {kid: jwk})}, per process.
_jwks_cache = {}


def reset_jwks_cache():
    _jwks_cache.clear()


async def _key_for(jwks_uri, kid):
    """
    The signing key for `kid`. A cache miss on the kid forces exactly one
    refetch, which is what makes provider key rotation a non-event; a refetch
    failure falls back to the warm cache when we have one.
    """
    cached = _jwks_cache.get(jwks_uri)
    fresh = cached and (time.time() - cached[0]) < JWKS_TTL_SECONDS
    if fresh and kid in cached[1]:
        return cached[1][kid]
    try:
        keys = await fetch_jwks(jwks_uri)
        _jwks_cache[jwks_uri] = (time.time(), keys)
    except OIDCError:
        if cached and kid in cached[1]:
            return cached[1][kid]
        raise
    if kid not in keys:
        raise OIDCError("no signing key for kid {}".format(kid))
    return keys[kid]


def _expected_issuer(provider, unverified_claims):
    """
    The issuer this token must carry. Entra's multi-tenant issuer is templated
    per tenant, so a configured `{tenantid}` placeholder is substituted with the
    token's own `tid` -- Microsoft's documented validation for the `common`
    endpoint.
    """
    issuer = provider.issuer
    if "{tenantid}" in issuer:
        tid = unverified_claims.get("tid")
        if not tid:
            raise OIDCError("multi-tenant issuer but the token carries no tid")
        issuer = issuer.replace("{tenantid}", str(tid))
    return issuer


async def validate_id_token(provider, id_token, nonce, jwks_uri):
    """Verify the ID token end to end and return its claims."""
    try:
        header = jwt.get_unverified_header(id_token)
        unverified = jwt.decode(id_token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise OIDCError("malformed id_token: {}".format(exc))

    if header.get("alg") not in ALLOWED_ALGORITHMS:
        raise OIDCError("id_token alg {} is not allowed".format(header.get("alg")))
    kid = header.get("kid")
    if not kid:
        raise OIDCError("id_token carries no kid")

    jwk = await _key_for(jwks_uri, kid)
    try:
        key = RSAAlgorithm.from_jwk(jwk if isinstance(jwk, str) else json.dumps(jwk))
    except Exception as exc:
        raise OIDCError("unusable signing key: {}".format(exc))

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=provider.client_id,
            issuer=_expected_issuer(provider, unverified),
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise OIDCError("id_token rejected: {}".format(exc))

    # A multi-audience token must name us as the authorized party.
    audience = claims.get("aud")
    if isinstance(audience, list) and len(audience) > 1:
        if claims.get("azp") != provider.client_id:
            raise OIDCError("multi-audience id_token with a foreign azp")

    if not hmac.compare_digest(str(claims.get("nonce") or ""), str(nonce or "")):
        raise OIDCError("id_token nonce does not match the transaction")

    return claims


def email_domain(email):
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].strip().lower()


def check_domain(provider, claims):
    """
    Enforce the provider's domain restriction, on every login and every link --
    not only at provisioning -- so a user removed from the workspace loses SSO
    access on their next attempt.

    Google issuers are enforced on the `hd` claim *inside the verified token*
    (the `hd` request parameter is a UI hint and is never trusted). Every other
    issuer is enforced on a verified email address.
    """
    if not provider.allowed_domains:
        return True
    if provider.is_google:
        hd = (claims.get("hd") or "").strip().lower()
        return bool(hd) and hd in provider.allowed_domains
    if not claims.get("email_verified"):
        return False
    domain = email_domain(claims.get("email"))
    return bool(domain) and domain in provider.allowed_domains
