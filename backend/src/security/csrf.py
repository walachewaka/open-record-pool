"""
Origin-check CSRF middleware (MOO-89).

Pure ASGI. For unsafe methods, if an Origin header is present and not in the
allow-list, reject with 403. Requests with NO Origin header pass (curl / CLI /
harness clients cannot be CSRF'd; browsers always send Origin on unsafe
cross-origin requests), so no client-side token plumbing is needed. This is
defence-in-depth behind the SameSite=Lax cookie.
"""
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from src.config import parse_allowed_origins

_UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


def _self_origin(scope):
    """
    The API's own origin. Same-origin unsafe requests are by definition not
    cross-site, and the embedded Grafana document (MOO-83) is served FROM this
    origin: its JS POSTs /admin/grafana/api/ds/query with Origin set to the
    backend itself, which is not an ALLOW_ORIGINS entry.
    """
    headers = Headers(scope=scope)
    host = headers.get("host")
    if not host:
        return None
    return "{}://{}".format(scope.get("scheme") or "http", host)


class OriginCheckMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") in _UNSAFE:
            origin = Headers(scope=scope).get("origin")
            allowed = parse_allowed_origins() + [_self_origin(scope)]
            if origin and origin not in allowed:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected."},
                )
                return await response(scope, receive, send)
        await self.app(scope, receive, send)
