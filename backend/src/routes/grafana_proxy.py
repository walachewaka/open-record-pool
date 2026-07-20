"""
The authenticated Grafana reverse proxy (MOO-83 D1).

Grafana is NEVER published: its port is docker-internal only (SECURITY.md 8),
and the single way to reach it is this route, behind
require_permission("view_reports") -- so embedding the dashboards cannot bypass
ORP's authorization (SECURITY.md 1), and it keeps working behind a TLS proxy
where a second published port would not.

Identity is passed with Grafana's auth.proxy: we inject X-WEBAUTH-USER (and a
Role header) after STRIPPING any client-supplied X-WEBAUTH-* header, which is
the header-injection defence that makes the whole scheme safe. ORP's own session
cookie is never forwarded upstream.
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from src.auth.permissions import require_permission
from src.schemas.users import UserOutSchema

router = APIRouter()

GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://grafana:3000").rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("GRAFANA_PROXY_TIMEOUT_SECONDS", "30"))

# Hop-by-hop headers never travel through a proxy, plus the two we own: the
# client's Cookie (Grafana does not need ORP's session) and any attempt to
# forge the auth.proxy identity.
_DROP_REQUEST_HEADERS = frozenset(
    [
        "host",
        "cookie",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
    ]
)
_DROP_RESPONSE_HEADERS = frozenset(
    [
        "connection",
        "keep-alive",
        "transfer-encoding",
        "upgrade",
        # The security middleware sets the frame policy for this prefix; a
        # Grafana-sent DENY would break the admin panel's iframe.
        "x-frame-options",
        "content-security-policy",
    ]
)

_client = None


def _get_client():
    global _client
    if _client is None:
        import httpx

        _client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False)
    return _client


async def close_grafana_client():
    """App shutdown hook."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None


def _upstream_headers(request: Request, user) -> dict:
    headers = {}
    for name, value in request.headers.items():
        lowered = name.lower()
        if lowered in _DROP_REQUEST_HEADERS or lowered.startswith("x-webauth-"):
            continue
        headers[name] = value
    # auth.proxy identity. Owners administer Grafana; everyone else who cleared
    # view_reports gets a read-only Viewer.
    headers["X-WEBAUTH-USER"] = str(getattr(user, "username", "") or "orp")
    headers["X-WEBAUTH-ROLE"] = (
        "Admin" if getattr(user, "role", None) == "owner" else "Viewer"
    )
    return headers


@router.api_route(
    "/admin/grafana/{path:path}",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def grafana_proxy(
    path: str,
    request: Request,
    current_user: UserOutSchema = Depends(require_permission("view_reports")),
):
    """Stream one request through to Grafana and its answer back."""
    import httpx

    client = _get_client()
    url = GRAFANA_URL + request.url.path
    if request.url.query:
        url += "?" + request.url.query

    upstream_request = client.build_request(
        request.method,
        url,
        headers=_upstream_headers(request, current_user),
        content=request.stream(),
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="Grafana upstream timeout")
    except Exception:
        raise HTTPException(status_code=502, detail="Grafana is not reachable")

    headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() not in _DROP_RESPONSE_HEADERS
    }
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=headers,
        background=BackgroundTask(upstream.aclose),
    )
