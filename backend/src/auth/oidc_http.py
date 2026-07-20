"""
Outbound HTTP to the identity providers (MOO-88).

Everything the backend fetches from an IDP goes through here: the discovery
document, the token endpoint, and the JWKS. All three are async httpx calls
(no sync HTTP in a request handler), never follow redirects, and are bounded by
a 10 s timeout.

SSRF containment (SECURITY.md item 9): the only URLs we ever fetch are the
configured discovery URL of a configured provider and the endpoints that
document advertises, and in production every one of them must be https. The
discovery document is cached for an hour per process.

CLIENT_FACTORY is the seam the SSO harness replaces with an ASGI-transport
client pointed at its in-process mock IDP, so the whole flow is testable
without sockets.
"""
import base64
import time

import httpx

from src.config import is_production

TIMEOUT_SECONDS = 10
DISCOVERY_TTL_SECONDS = 3600


def default_client():
    return httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False)


CLIENT_FACTORY = default_client

# {provider_id: (fetched_at, metadata)} and {provider_id: "ok"|"error"}, both
# per process. The status is what the admin SSO page reports.
_discovery_cache = {}
_discovery_status = {}


class OIDCError(Exception):
    """An IDP interaction failed. Never surfaced verbatim to the browser."""


def discovery_status(provider_id):
    return _discovery_status.get(provider_id, "unchecked")


def reset_caches():
    """Drop the per-process caches (tests, and after a config reload)."""
    _discovery_cache.clear()
    _discovery_status.clear()


def _assert_fetchable(url):
    if not url or not (url.startswith("https://") or url.startswith("http://")):
        raise OIDCError("provider URL is not http(s)")
    if is_production() and not url.startswith("https://"):
        raise OIDCError("provider URL must be https in production")


async def _get_json(url):
    _assert_fetchable(url)
    client = CLIENT_FACTORY()
    try:
        response = await client.get(url)
        if response.status_code != 200:
            raise OIDCError("GET {} returned {}".format(url, response.status_code))
        return response.json()
    except OIDCError:
        raise
    except Exception as exc:
        raise OIDCError("GET {} failed: {}".format(url, exc))
    finally:
        await client.aclose()


async def fetch_discovery(provider):
    """The provider's OIDC metadata document (cached for an hour)."""
    cached = _discovery_cache.get(provider.id)
    if cached and (time.time() - cached[0]) < DISCOVERY_TTL_SECONDS:
        return cached[1]
    try:
        metadata = await _get_json(provider.discovery_url)
    except OIDCError:
        _discovery_status[provider.id] = "error"
        if cached:
            # Stale metadata beats refusing every login while the IDP hiccups.
            return cached[1]
        raise
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not metadata.get(key):
            _discovery_status[provider.id] = "error"
            raise OIDCError("discovery document has no {}".format(key))
    _discovery_cache[provider.id] = (time.time(), metadata)
    _discovery_status[provider.id] = "ok"
    return metadata


async def fetch_jwks(jwks_uri):
    """The provider's signing keys as {kid: jwk}."""
    document = await _get_json(jwks_uri)
    keys = {}
    for key in document.get("keys") or []:
        kid = key.get("kid")
        if kid:
            keys[kid] = key
    if not keys:
        raise OIDCError("JWKS has no usable keys")
    return keys


async def exchange_code(provider, code, code_verifier, redirect_uri):
    """
    Trade the authorization code for the token response. The client secret goes
    in the HTTP Basic header (accepted by Entra, Google and Okta); the redirect
    URI is the configured one, never derived from the request's Host header.
    """
    metadata = await fetch_discovery(provider)
    token_endpoint = metadata["token_endpoint"]
    _assert_fetchable(token_endpoint)
    basic = base64.b64encode(
        "{}:{}".format(provider.client_id, provider.client_secret).encode("utf-8")
    ).decode("ascii")
    client = CLIENT_FACTORY()
    try:
        response = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "client_id": provider.client_id,
            },
            headers={"Authorization": "Basic {}".format(basic)},
        )
    except Exception as exc:
        raise OIDCError("token exchange failed: {}".format(exc))
    finally:
        await client.aclose()

    if response.status_code != 200:
        raise OIDCError("token endpoint returned {}".format(response.status_code))
    try:
        payload = response.json()
    except Exception:
        raise OIDCError("token endpoint returned a non-JSON body")
    if not payload.get("id_token"):
        raise OIDCError("token response carries no id_token")
    # The access/refresh tokens are deliberately dropped on the floor: the
    # provider tokens are used once, for identity (MOO-88 D10).
    return payload["id_token"]
