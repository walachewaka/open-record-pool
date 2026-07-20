"""
Security-header middleware for the backend (API) origin (MOO-89).

Pure ASGI (not BaseHTTPMiddleware) so it never buffers a streaming/Range audio
response: it only rewrites the http.response.start headers.

The API serves JSON and audio, never HTML, so its CSP is the hard lock-down
`default-src 'none'; frame-ancestors 'none'`. HSTS is emitted only when the
cookie is Secure (TLS on).

The single exception is the Grafana proxy prefix (MOO-83): it DOES serve HTML,
and the admin panel embeds it in an iframe, so those responses swap the DENY
frame policy for `frame-ancestors 'self' <ALLOW_ORIGINS>` -- the admin origin
may frame it, nobody else may.
"""
from starlette.datastructures import MutableHeaders

from src.config import parse_allowed_origins, resolve_cookie_secure

GRAFANA_PREFIX = "/admin/grafana"


def _grafana_csp():
    origins = " ".join(sorted(parse_allowed_origins()))
    return "frame-ancestors 'self' {}".format(origins).strip()


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        secure = resolve_cookie_secure()
        embedded = (scope.get("path") or "").startswith(GRAFANA_PREFIX)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                if embedded:
                    # X-Frame-Options has no allow-list form; the CSP directive
                    # is the one that lets exactly our own admin panel frame it.
                    del headers["X-Frame-Options"]
                    headers["Content-Security-Policy"] = _grafana_csp()
                else:
                    headers.setdefault("X-Frame-Options", "DENY")
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'none'; frame-ancestors 'none'",
                    )
                if headers.get("content-type", "").startswith("application/json"):
                    headers.setdefault("Cache-Control", "no-store")
                if secure:
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
